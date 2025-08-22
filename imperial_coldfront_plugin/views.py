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
from coldfront.core.project.models import (
    Project,
    ProjectStatusChoice,
    ProjectUser,
    ProjectUserRoleChoice,
    ProjectUserStatusChoice,
)
from coldfront.core.resource.models import Resource
from coldfront.core.user.utils import UserSearch
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
from django_q.tasks import Chain, Task

from .dart import create_dart_id_attribute
from .forms import (
    DartIDForm,
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


def get_next_rdf_project_id():
    """Get the next available RDF project id value."""
    rdf_id_attribute_type = AllocationAttributeType.objects.get(name="RDF Project ID")
    group_ids = AllocationAttribute.objects.filter(
        allocation_attribute_type=rdf_id_attribute_type,
    ).values_list("value", flat=True)
    id_numbers = [
        int(PROJECT_ID_REGEX.match(group_id).groupdict()["number"])
        for group_id in group_ids
    ]
    new_project_number = max(id_numbers) + 1 if id_numbers else 1

    return format_project_number_to_id(new_project_number)


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
            dart_id = form.cleaned_data["dart_id"]

            rdf_id_attribute_type = AllocationAttributeType.objects.get(
                name="RDF Project ID"
            )
            project_id = get_next_rdf_project_id()
            if AllocationAttribute.objects.filter(
                allocation_attribute_type=rdf_id_attribute_type,
                value=project_id,
            ):
                raise ValueError("RDF project with ID already exists.")

            rdf_resource = Resource.objects.get(name="RDF Active")

            allocation_active_status = AllocationStatusChoice.objects.get(name="Active")

            # We create a new user and an associated project, if they don't exist.
            project = get_or_create_project(form.cleaned_data["user"])

            rdf_allocation = Allocation.objects.create(
                project=project,
                status=allocation_active_status,
                quantity=1,
                start_date=timezone.now().date(),
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
                allocation_attribute_type=rdf_id_attribute_type,
                allocation=rdf_allocation,
                value=project_id,
            )

            create_dart_id_attribute(dart_id, rdf_allocation)

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
                    project_id,
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
                    fileset_name=project_id,
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
