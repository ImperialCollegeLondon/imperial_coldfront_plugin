"""Plugin views."""

import re
from pathlib import Path

from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
    AllocationAttributeUsage,
    AllocationStatusChoice,
    AllocationUserStatusChoice,
)
from coldfront.core.project.forms import ProjectAddUserForm
from coldfront.core.project.models import (
    Project,
    ProjectStatusChoice,
    ProjectUser,
    ProjectUserRoleChoice,
    ProjectUserStatusChoice,
)
from coldfront.core.project.views import ProjectAddUsersSearchResultsView
from coldfront.core.resource.models import Resource
from coldfront.core.user.utils import CombinedUserSearch, UserSearch
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django_q.tasks import Chain, Task

from .dart import create_dart_id_attribute
from .forms import (
    DartIDForm,
    ProjectAddUsersToAllocationShortnameForm,
    ProjectCreationForm,
    RDFAllocationForm,
    get_department_choices,
)
from .gid import get_new_gid
from .microsoft_graph_client import get_graph_api_client
from .policy import check_project_pi_or_superuser, user_eligible_for_hpc_access

User = get_user_model()


class GraphAPISearch(UserSearch):
    """Search for users using MS Graph API."""

    search_source = "GraphAPI"

    def search_a_user(
        self, user_search_string: str | None = None, search_by: str = "all_fields"
    ) -> list[str]:
        """Searchers for a single user.

        Args:
            user_search_string: The user string to look for.
            search_by: (Unused) Fields to look into. This backend always looks into the
                user's name or username.
        """
        graph_client = get_graph_api_client()
        found = graph_client.user_search_by(user_search_string, search_by)
        for user in found:
            user["source"] = self.search_source
        return list(filter(user_eligible_for_hpc_access, found))


PROJECT_ID_PREFIX = "rdf-"
PROJECT_ID_REGEX = re.compile(PROJECT_ID_PREFIX + r"(?P<number>\d{6})")


def format_project_number_to_id(num):
    """Format an rdf project number into a full id string."""
    return f"{PROJECT_ID_PREFIX}{num:06d}"


@login_required
def add_rdf_storage_allocation(request):
    """Create a new RDF project allocation."""
    if not request.user.is_superuser:
        return HttpResponseForbidden()

    if request.method == "POST":
        form = RDFAllocationForm(request.POST)
        if form.is_valid():
            storage_size_tb = form.cleaned_data["size"]
            faculty = form.cleaned_data["faculty"]
            department = form.cleaned_data["department"]
            # dart_id = form.cleaned_data["dart_id"]
            project = form.cleaned_data["project"]
            shortname = form.cleaned_data["allocation_shortname"]
            ldap_name = f"{settings.LDAP_SHORTNAME_PREFIX}{shortname}"

            shortname_attribute_type = AllocationAttributeType.objects.get(
                name="Shortname"
            )
            rdf_resource = Resource.objects.get(name="RDF Active")

            allocation_active_status = AllocationStatusChoice.objects.get(name="Active")
            rdf_allocation = Allocation.objects.create(
                project=project,
                status=allocation_active_status,
                start_date=form.cleaned_data["start_date"],
                end_date=form.cleaned_data["end_date"],
                is_changeable=True,
            )
            rdf_allocation.resources.add(rdf_resource)

            storage_quota_attribute_type = AllocationAttributeType.objects.get(
                name="Storage Quota (TB)"
            )
            quota_attribute = AllocationAttribute.objects.create(
                allocation_attribute_type=storage_quota_attribute_type,
                allocation=rdf_allocation,
                value=storage_size_tb,
            )
            AllocationAttributeUsage.objects.create(
                allocation_attribute=quota_attribute, value=0
            )

            files_quota_attribute_type = AllocationAttributeType.objects.get(
                name="Files Quota"
            )
            files_attribute = AllocationAttribute.objects.create(
                allocation_attribute_type=files_quota_attribute_type,
                allocation=rdf_allocation,
                value=settings.GPFS_FILES_QUOTA,
            )
            AllocationAttributeUsage.objects.create(
                allocation_attribute=files_attribute, value=0
            )

            AllocationAttribute.objects.create(
                allocation_attribute_type=shortname_attribute_type,
                allocation=rdf_allocation,
                value=shortname,
            )

            # create_dart_id_attribute(dart_id, rdf_allocation)

            gid_attribute_type = AllocationAttributeType.objects.get(name="GID")
            gid = get_new_gid()
            AllocationAttribute.objects.create(
                allocation_attribute_type=gid_attribute_type,
                allocation=rdf_allocation,
                value=gid,
            )

            chain = Chain()
            if settings.LDAP_ENABLED:
                chain.append(
                    "imperial_coldfront_plugin.ldap._ldap_create_group",
                    ldap_name,
                    gid,
                )

            allocation_user_active_status = AllocationUserStatusChoice.objects.get(
                name="Active"
            )

            chain.append(
                "coldfront.core.allocation.models.AllocationUser.objects.create",
                allocation=rdf_allocation,
                user=project.pi,
                status=allocation_user_active_status,
            )

            if settings.GPFS_ENABLED:
                parent_fileset_path = Path(
                    settings.GPFS_FILESYSTEM_MOUNT_PATH,
                    settings.GPFS_FILESYSTEM_NAME,
                    settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES,
                    faculty,
                )
                relative_projects_path = Path(department)

                chain.append(
                    "imperial_coldfront_plugin.gpfs_client._create_fileset_set_quota",
                    filesystem_name=settings.GPFS_FILESYSTEM_NAME,
                    owner_id="root",
                    group_id="root",
                    fileset_name=shortname,
                    parent_fileset_path=parent_fileset_path,
                    relative_projects_path=relative_projects_path,
                    permissions=settings.GPFS_PERMISSIONS,
                    block_quota=f"{storage_size_tb}T",
                    files_quota=settings.GPFS_FILES_QUOTA,
                    parent_fileset=faculty,
                )

            group = chain.run()
            messages.success(request, "RDF allocation created successfully.")
            return redirect(
                "imperial_coldfront_plugin:list_tasks",
                group=group,
                allocation_pk=rdf_allocation.pk,
            )
    else:
        form = RDFAllocationForm()
    return render(
        request, "imperial_coldfront_plugin/rdf_allocation_form.html", dict(form=form)
    )


def load_departments(request):
    """Loads the available departments for a given faculty."""
    faculty = request.GET.get("faculty")
    departments = get_department_choices(faculty)
    return render(
        request,
        "imperial_coldfront_plugin/departments_list.html",
        {"departments": departments},
    )


@login_required
def task_stat_view(request, group: str, allocation_pk: int):
    """Displays a list of tasks and their status."""
    from django_q.models import OrmQ

    if not request.user.is_superuser:
        return HttpResponseForbidden()

    queued = [qt.task() for qt in OrmQ.objects.all() if qt.task()["group"] == group]
    completed = Task.objects.filter(group=group).order_by("started").reverse()

    return render(
        request,
        "imperial_coldfront_plugin/task_list.html",
        context={
            "completed": completed,
            "queued": queued,
            "allocation_pk": allocation_pk,
        },
    )


def get_or_create_project(user: User) -> Project:
    """Get project from the database or creates one.

    Args:
        user: The user object that will own a project.

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
def add_dart_id_to_allocation(request: HttpRequest, allocation_pk: int):
    """Dedicated view function to add dart ids to an allocation."""
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
    """Create a new project from the form data."""
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
    return project_obj


@login_required
def project_creation(request: HttpRequest):
    """View to create a new project for any user."""
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

    def post(self, request, *args, **kwargs):
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
