"""Plugin views."""

import re
from pathlib import Path
from typing import TYPE_CHECKING

from coldfront.core.allocation.models import Allocation
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
from django.forms import formset_factory
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django_q.tasks import async_task, fetch

from .dart import create_dart_id_attribute
from .forms import (
    CreditTransactionForm,
    DartIDForm,
    ProjectAddUsersToAllocationShortnameForm,
    ProjectCreationForm,
    RDFAllocationForm,
    get_department_choices,
)
from .microsoft_graph_client import get_graph_api_client
from .policy import check_project_pi_or_superuser, user_eligible_for_hpc_access
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


def create_new_project(form: ProjectCreationForm) -> Project:
    """Create a new project from the form data.

    Args:
      form: The validated project creation form.

    Returns:
        The newly created project.
    """
    from coldfront.core.project.models import ProjectAttribute, ProjectAttributeType

    project_obj = form.save(commit=False)
    project_obj.status = ProjectStatusChoice.objects.get(name="Active")
    project_obj.pi = form.cleaned_data["user"]
    project_obj.save()
    ProjectUser.objects.create(
        user=form.cleaned_data["user"],
        project=project_obj,
        role=ProjectUserRoleChoice.objects.get(name="Manager"),
        status=ProjectUserStatusChoice.objects.get(name="Active"),
    )
    group_id_attribute_type = ProjectAttributeType.objects.get(name="Group ID")
    location_attribute_type = ProjectAttributeType.objects.get(
        name="Filesystem location"
    )
    department_attribute_type = ProjectAttributeType.objects.get(name="Department")
    faculty_attribute_type = ProjectAttributeType.objects.get(name="Faculty")
    ProjectAttribute.objects.create(
        proj_attr_type=department_attribute_type,
        project=project_obj,
        value=form.cleaned_data["department"],
    )
    ProjectAttribute.objects.create(
        proj_attr_type=faculty_attribute_type,
        project=project_obj,
        value=form.cleaned_data["faculty"],
    )
    ProjectAttribute.objects.create(
        proj_attr_type=group_id_attribute_type,
        project=project_obj,
        value=form.cleaned_data["group_id"],
    )
    ProjectAttribute.objects.create(
        proj_attr_type=location_attribute_type,
        project=project_obj,
        value=str(
            Path(
                settings.GPFS_FILESYSTEM_MOUNT_PATH,
                settings.GPFS_FILESYSTEM_NAME,
                settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES,
                form.cleaned_data["faculty"],
                form.cleaned_data["department"],
                form.cleaned_data["group_id"],
            )
        ),
    )
    if ticket_id := form.cleaned_data.get("ticket_id"):
        ticket_attribute_type = ProjectAttributeType.objects.get(
            name="ASK Ticket Reference"
        )
        ProjectAttribute.objects.create(
            proj_attr_type=ticket_attribute_type, project=project_obj, value=ticket_id
        )

    return project_obj


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
        form = ProjectCreationForm(request.POST)
        if form.is_valid():
            project = create_new_project(form)
            return redirect("project-detail", pk=project.pk)
    else:
        form = ProjectCreationForm()
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
            transaction = form.save()
            return redirect("project-detail", pk=transaction.project.pk)
    else:
        form = CreditTransactionForm()
    return render(
        request,
        "imperial_coldfront_plugin/credit_transaction_form.html",
        context=dict(form=form),
    )
