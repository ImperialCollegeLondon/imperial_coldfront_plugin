"""Plugin views."""

import re
from typing import TYPE_CHECKING

from coldfront.core.allocation.models import Allocation, AllocationStatusChoice
from coldfront.core.project.forms import ProjectAddUserForm
from coldfront.core.project.models import (
    Project,
    ProjectStatusChoice,
    ProjectUser,
    ProjectUserRoleChoice,
    ProjectUserStatusChoice,
)
from coldfront.core.project.views import ProjectAddUsersSearchResultsView
from coldfront.core.user.utils import CombinedUserSearch, UserSearch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.forms import ModelChoiceField, formset_factory
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django_q.tasks import async_task, fetch

from .dart import create_dart_id_attribute
from .forms import (
    AdminProjectCreationForm,
    CreditTransactionForm,
    DartIDForm,
    HX2TermsAndConditionsForm,
    ProjectAddUsersToAllocationShortnameForm,
    RDFAllocationForm,
    UserProjectCreationForm,
    get_department_choices,
)
from .microsoft_graph_client import get_graph_api_client
from .models import CreditTransaction, HX2Allocation, ICLProject
from .policy import (
    check_project_pi_or_superuser,
    user_eligible_for_hpc_access,
    user_eligible_to_be_pi,
)
from .tasks import create_rdf_allocation

if TYPE_CHECKING:
    from django.contrib.auth.models import User as UserType

    class AuthenticatedHttpRequest(HttpRequest):
        """An HttpRequest class with a logged in user."""

        user: UserType


User = get_user_model()


class GraphAPISearch(UserSearch):
    """Search for users using MS Graph API."""

    search_source = "GraphAPI"

    def search_a_user(
        self, user_search_string: str | None = None, search_by: str = "all_fields"
    ) -> list[dict[str, str]]:
        """Searchers for a single user.

        Args:
            user_search_string: The user string to look for.
            search_by: (Unused) Fields to look into. This backend always looks into the
                user's name or username.

        Returns:
            A list of user profiles matching the search criteria.
        """
        graph_client = get_graph_api_client()
        found = graph_client.user_search_by(user_search_string, search_by)
        for user in found:
            user["source"] = self.search_source
        return [user for user in found if user_eligible_for_hpc_access(user)]


PROJECT_ID_PREFIX = "rdf-"
PROJECT_ID_REGEX = re.compile(PROJECT_ID_PREFIX + r"(?P<number>\d{6})")


@login_required
def add_rdf_storage_allocation(request: HttpRequest) -> HttpResponse:
    """Create a new RDF project allocation.

    Args:
      request: The HTTP request object.

    Returns:
      The page for the allocation creation form or redirects to the task result page.
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden()

    if request.method == "POST":
        form = RDFAllocationForm(request.POST)
        if form.is_valid():
            task_id = async_task(create_rdf_allocation, form.cleaned_data)
            return redirect(
                "imperial_coldfront_plugin:allocation_task_result",
                task_id=task_id,
                shortname=form.cleaned_data["allocation_shortname"],
            )
    else:
        form = RDFAllocationForm()
    return render(
        request, "imperial_coldfront_plugin/rdf_allocation_form.html", dict(form=form)
    )


def load_departments(request: HttpRequest) -> HttpResponse:
    """Loads the available departments for a given faculty.

    Args:
      request: The HTTP request object.

    Returns:
      The partial HTML to populate the departments dropdown.
    """
    faculty = request.GET["faculty"]
    departments = get_department_choices(faculty)
    return render(
        request,
        "imperial_coldfront_plugin/departments_list.html",
        {"departments": departments},
    )


@login_required
def allocation_task_result(
    request: HttpRequest, task_id: str, shortname: str
) -> HttpResponse:
    """Display information about an rdf allocation creation task.

    Args:
      request: The HTTP request object.
      task_id: The ID of the task to fetch.
      shortname: The shortname of the allocation being created.

    Returns:
      The page displaying the task result.
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    task = fetch(task_id)
    return render(
        request,
        "imperial_coldfront_plugin/allocation_task_result.html",
        context={"task": task, "shortname": shortname},
    )


def get_or_create_project(user: "UserType") -> Project:
    """Get project from the database or creates one.

    Args:
        user: The user object that will owner a project.

    Return:
        The project, already existing or newly created.
    """
    project, project_created = Project.objects.get_or_create(
        pi=user,
        defaults=dict(
            title=f"{user.get_full_name()}'s Research Group",
            status=ProjectStatusChoice.objects.get_or_create(name="Active")[0],
        ),
    )
    if project_created:
        ProjectUser.objects.create(
            user=user,
            project=project,
            role=ProjectUserRoleChoice.objects.get_or_create(name="Manager")[0],
            status=ProjectUserStatusChoice.objects.get_or_create(name="Active")[0],
        )
    return project


@login_required
def add_dart_id_to_allocation(
    request: "AuthenticatedHttpRequest", allocation_pk: int
) -> HttpResponse:
    """Dedicated view function to add dart ids to an allocation.

    Args:
      request: The HTTP request object.
      allocation_pk: The primary key of the allocation to add the dart id to.

    Returns:
      The page for the dart id form or redirects to the allocation detail page.
    """
    allocation = get_object_or_404(Allocation, pk=allocation_pk)
    check_project_pi_or_superuser(allocation.project, request.user)

    if request.method == "POST":
        form = DartIDForm(request.POST)
        if form.is_valid():
            create_dart_id_attribute(form.cleaned_data["dart_id"], allocation)
            return redirect(reverse("allocation-detail", args=[allocation_pk]))
    else:
        form = DartIDForm()
    return render(
        request, "imperial_coldfront_plugin/dart_id_form.html", context=dict(form=form)
    )


@login_required
def project_creation(request: HttpRequest) -> HttpResponse:
    """View to create a new project for any user.

    Args:
      request: The HTTP request object.

    Returns:
      The page for the project creation form or redirects to the new project page.
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden()

    if request.method == "POST":
        form = AdminProjectCreationForm(request.POST)
        if form.is_valid():
            project = ICLProject.objects.create_iclproject(
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                field_of_science=form.cleaned_data["field_of_science"],
                user=form.cleaned_data["user"],
                faculty=form.cleaned_data["faculty"],
                department=form.cleaned_data["department"],
                group_id=form.cleaned_data["group_id"],
                ticket_id=form.cleaned_data["ticket_id"],
            )
            return redirect("project-detail", pk=project.pk)
    else:
        form = AdminProjectCreationForm()
    return render(
        request,
        "imperial_coldfront_plugin/project_creation_form.html",
        context=dict(form=form),
    )


@login_required
def user_project_creation(request: "AuthenticatedHttpRequest") -> HttpResponse:
    """View to create a new project for the logged in user.

    Args:
      request: The HTTP request object.

    Returns:
      The page for the project creation form or redirects to the new project page.
    """
    if not settings.ENABLE_USER_GROUP_CREATION:
        return HttpResponseForbidden()

    if not request.user.is_superuser:
        if Project.objects.filter(pi=request.user).exists():
            return HttpResponseForbidden()
        user_profile = get_graph_api_client().user_profile(request.user.username)
        if not user_eligible_to_be_pi(user_profile):
            return HttpResponseForbidden()

    if request.method == "POST":
        form = UserProjectCreationForm(request.POST)
        if form.is_valid():
            project = ICLProject.objects.create_iclproject(
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                field_of_science=form.cleaned_data["field_of_science"],
                user=request.user,
                faculty=form.cleaned_data["faculty"],
                department=form.cleaned_data["department"],
                group_id=request.user.username,
            )
            return redirect("project-detail", pk=project.pk)
    else:
        form = UserProjectCreationForm()
    return render(
        request,
        "imperial_coldfront_plugin/project_creation_form.html",
        context=dict(form=form),
    )


class ProjectAddUsersSearchResultsShortnameView(ProjectAddUsersSearchResultsView):
    """View to search for users to add to a project, with allocation shortname.

    This is an override of the Coldfront view due to the need to customise the display
    of allocation attributes. Unfortunately most of the code is a copy-paste job with
    only the allocation form being updated to customise the display.
    """

    template_name = "imperial_coldfront_plugin/project_add_user_search_results.html"

    # As mentioned in doc string this is copy pasted code so we ignore the type checking
    # errors so we don't have to change it and risk breaking something.
    def post(self, request, *args, **kwargs):  # type: ignore[no-untyped-def]
        """Handle POST requests: process the search form and display results."""
        user_search_string = request.POST.get("q")
        search_by = request.POST.get("search_by")
        pk = self.kwargs.get("pk")

        project_obj = get_object_or_404(Project, pk=pk)

        users_to_exclude = [
            ele.user.username
            for ele in project_obj.projectuser_set.filter(status__name="Active")
        ]

        cobmined_user_search_obj = CombinedUserSearch(
            user_search_string, search_by, users_to_exclude
        )

        context = cobmined_user_search_obj.search()

        matches = context.get("matches")
        for match in matches:
            match.update({"role": ProjectUserRoleChoice.objects.get(name="User")})

        if matches:
            formset = formset_factory(ProjectAddUserForm, max_num=len(matches))
            formset = formset(initial=matches, prefix="userform")
            context["formset"] = formset
            context["user_search_string"] = user_search_string
            context["search_by"] = search_by

        if len(user_search_string.split()) > 1:
            users_already_in_project = []
            for ele in user_search_string.split():
                if ele in users_to_exclude:
                    users_already_in_project.append(ele)
            context["users_already_in_project"] = users_already_in_project

        # The following block of code is used to hide/show the allocation div.
        if project_obj.allocation_set.filter(
            status__name__in=["Active", "New", "Renewal Requested"]
        ).exists():
            div_allocation_class = "placeholder_div_class"
        else:
            div_allocation_class = "d-none"
        context["div_allocation_class"] = div_allocation_class
        ###

        allocation_form = ProjectAddUsersToAllocationShortnameForm(
            request.user, project_obj.pk, prefix="allocationform"
        )
        context["pk"] = pk
        context["allocation_form"] = allocation_form
        return render(request, self.template_name, context)


@login_required
def create_credit_transaction(request: HttpRequest) -> HttpResponse:
    """Create a new credit transaction.

    Args:
      request: The HTTP request object.

    Returns:
      The page for the credit transaction form or redirects to project detail.
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden()

    if request.method == "POST":
        form = CreditTransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.authoriser = request.user.username
            transaction.save()
            return redirect("project-detail", pk=transaction.project.pk)
    else:
        form = CreditTransactionForm()

    return render(
        request,
        "imperial_coldfront_plugin/credit_transaction_form.html",
        context=dict(form=form),
    )


@login_required
def project_credit_transactions(
    request: "AuthenticatedHttpRequest", pk: int
) -> HttpResponse:
    """Display all credit transactions for a project with running balance."""
    project = get_object_or_404(Project, pk=pk)
    check_project_pi_or_superuser(project, request.user)

    transactions = CreditTransaction.objects.filter(project=project).order_by(
        "timestamp", "id"
    )

    running = 0
    rows: list[dict[str, int | str | CreditTransaction]] = []
    for transaction in transactions:
        running += transaction.amount
        rows.append(
            {
                "transaction": transaction,
                "running_balance": running,
                "authoriser": transaction.authoriser,
            }
        )

    return render(
        request,
        "imperial_coldfront_plugin/project_credit_transactions.html",
        context={
            "project": project,
            "rows": rows,
            "total_balance": running,
        },
    )


@login_required
def user_create_hx2_allocation(request: "AuthenticatedHttpRequest") -> HttpResponse:
    """Create an HX2 allocation for the user."""
    if not settings.ENABLE_USER_GROUP_CREATION:
        return HttpResponseForbidden()

    if Allocation.objects.filter(
        project__pi=request.user,
        status__name="Active",
        resources__name="HX2",
    ).exists():
        # render info page saying user already has an active HX2 allocation
        return render(request, "imperial_coldfront_plugin/existing_hx2_allocation.html")

    form = HX2TermsAndConditionsForm(request.POST or None)

    # set the project choices queryset to only the projects of the user
    # this limits the selection to only the user's projects
    # it is also used in form validation to ensure the user can only create
    # allocations for their own projects
    projects = Project.objects.filter(pi=request.user, status__name="Active")
    project_field = form.fields["project"]
    if not isinstance(project_field, ModelChoiceField):
        # this keeps mypy happy as otherwise it won't allow setting the queryset on the
        # field as it doesn't know which Field subclass it is.
        raise TypeError("Expected 'project' field to be a ModelChoiceField.")
    project_field.queryset = projects

    if form.is_valid():
        allocation = HX2Allocation.objects.create_hx2allocation(
            project=form.cleaned_data["project"],
            status=AllocationStatusChoice.objects.get(name="Active"),
            quantity=1,
            start_date=timezone.now().date(),
            end_date=None,
            justification="User self-allocated Hx2 allocation",
            description="Provides access to HX2 for all allocation users.",
            is_locked=False,
            is_changeable=True,
        )
        return redirect(reverse("allocation-detail", args=[allocation.pk]))
    return render(
        request,
        "imperial_coldfront_plugin/hx2_allocation_self_creation.html",
        context=dict(form=form),
    )
