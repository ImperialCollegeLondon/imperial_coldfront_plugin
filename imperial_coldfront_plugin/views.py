"""Plugin views."""

import re
from datetime import timedelta
from pathlib import Path

from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
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
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import IntegrityError
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django_q.tasks import Chain, Task

from .emails import (
    send_group_access_granted_email,
    send_group_invite_email,
    send_manager_removed_email,
    send_member_promotion_to_manager_email,
)
from .forms import (
    GroupMembershipExtendForm,
    GroupMembershipForm,
    RDFAllocationForm,
    TermsAndConditionsForm,
    UserSearchForm,
    get_department_choices,
)
from .microsoft_graph_client import get_graph_api_client
from .models import GroupMembership, ResearchGroup
from .policy import (
    check_group_owner_manager_or_superuser,
    check_group_owner_or_superuser,
    user_already_has_hpc_access,
    user_eligible_for_hpc_access,
    user_eligible_to_be_pi,
)

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


@login_required
def research_group_terms_view(request: HttpRequest) -> HttpResponse:
    """View for accepting T&Cs and creating a ResearchGroup.

    TODO: Verify if superusers should be able to create research groups.

    Args:
        request: The Http request including the user information.

    Returns:
        The relevant Http response, depending on the permissions and the type of
        request.
    """
    graph_client = get_graph_api_client()
    user_profile = graph_client.user_profile(request.user.username)
    if not user_eligible_to_be_pi(user_profile) and not request.user.is_superuser:
        return HttpResponseForbidden("You are not allowed to create a research group.")
    elif GroupMembership.objects.filter(member=request.user).exists():
        return HttpResponseForbidden(
            "You cannot create a research group while being a member of another one.",
        )

    if request.method == "POST":
        form = TermsAndConditionsForm(request.POST)  # use TermsAndConditionsForm
        if form.is_valid():
            # Autogenerate name
            group_name = f"Research Group {request.user.username}"
            gid = generate_unique_gid()

            # If the group already exist, we just use that one
            group, created = ResearchGroup.objects.get_or_create(
                owner=request.user, defaults={"gid": gid, "name": group_name}
            )

            if created:
                messages.success(request, "Research group created successfully.")
            else:
                messages.success(
                    request,
                    f"A research group owned by '{request.user}' already exist.",
                )

            return redirect(
                reverse(
                    "imperial_coldfront_plugin:group_members",
                    kwargs=dict(group_pk=group.pk),
                )
            )
    else:
        form = TermsAndConditionsForm()  # use TermsAndConditionsForm

    return render(
        request, "imperial_coldfront_plugin/research_group_terms.html", {"form": form}
    )


def generate_unique_gid():
    """Generate a unique GID for the ResearchGroup."""
    last_gid = ResearchGroup.objects.order_by("-gid").first()
    return (last_gid.gid + 1) if last_gid else 1000  # Start at 1000 if no groups exist


@login_required
def group_members_view(request: HttpRequest, group_pk: int) -> HttpResponse:
    """Display the members of a research group for a specific user.

    This view retrieves and displays all members associated with a research group
    where the specified user (identified by `group_pk`) is the owner. Access is
    restricted to either the group owner, an administrator, or a manager.
    Unauthorised users will receive a permission denied response.

    Args:
        request (HttpRequest): The HTTP request object containing metadata about the
            request.
        group_pk (int): The primary key of the research group to be
            displayed.

    Returns:
        HttpResponse: If access is permitted, renders `group_members.html`
                        displaying the group members.
                        If the logged-in user is unauthorised, returns a
                        `HttpResponseForbidden`.

    Raises:
        Http404: If no group is found with the provided `group_pk`.
    """
    group = get_object_or_404(ResearchGroup, pk=group_pk)
    check_group_owner_manager_or_superuser(group, request.user)

    group_members = GroupMembership.objects.filter(group=group)
    is_manager = group_members.filter(member=request.user, is_manager=True).exists()
    current_date = timezone.now()

    return render(
        request,
        "group_members.html",
        {
            "group_members": group_members,
            "is_manager": is_manager,
            "group_pk": group_pk,
            "current_date": current_date,
        },
    )


@login_required
def check_access(request: HttpRequest):
    """Informational view displaying the user's current access to RCS resources."""
    if request.user.is_superuser:
        message = "You have access as an administrator."
    elif ResearchGroup.objects.filter(owner=request.user):
        message = "You have access as the owner of a HPC access group."
    else:
        try:
            group_membership = GroupMembership.objects.get(member=request.user)
            message = (
                "You have been granted access to the RCS compute cluster as a member "
                "of the research group of "
                f"{group_membership.group.owner.get_full_name()}."
            )
        except GroupMembership.DoesNotExist:
            message = "You do not currently have access to the RCS compute cluster."

    return render(
        request, "imperial_coldfront_plugin/check_access.html", dict(message=message)
    )


@login_required
def user_search(request: HttpRequest, group_pk: int) -> HttpResponse:
    """Simple search interface to find users eligible to join a ResearchGroup."""
    if request.method == "POST":
        form = UserSearchForm(request.POST)
        if form.is_valid():
            search_query = form.cleaned_data["search"]
            search_results = GraphAPISearch(search_query, "all_fields").search()
            filtered_results = [
                user
                for user in search_results
                if user_eligible_for_hpc_access(user)
                and not user_already_has_hpc_access(user["username"])
            ]
            return render(
                request,
                "imperial_coldfront_plugin/user_search.html",
                dict(form=form, search_results=filtered_results, group_pk=group_pk),
            )
    else:
        form = UserSearchForm()

    return render(
        request, "imperial_coldfront_plugin/user_search.html", dict(form=form)
    )


@login_required
def send_group_invite(request: HttpRequest, group_pk: int) -> HttpResponse:
    """Invite an individual to a group."""
    group = get_object_or_404(ResearchGroup, pk=group_pk)
    check_group_owner_manager_or_superuser(group, request.user)

    if request.method == "POST":
        form = GroupMembershipForm(request.POST)

        if form.is_valid():
            expiration = form.cleaned_data["expiration"]

            if expiration < timezone.now().date():
                return HttpResponseBadRequest("Expiration date should be in the future")

            username = form.cleaned_data["username"]
            if GroupMembership.objects.filter(member__username=username):
                return HttpResponseBadRequest("User already in a group")

            graph_client = get_graph_api_client()
            user_profile = graph_client.user_profile(username)

            if not user_eligible_for_hpc_access(
                user_profile
            ) or user_already_has_hpc_access(user_profile["username"]):
                return HttpResponseBadRequest("User not found or not eligible")

            invitee_email = user_profile["email"]

            # Create invitation URL.
            signer = TimestampSigner()
            token = signer.sign_object(
                {
                    "expiration": expiration.isoformat(),
                    "group_pk": group.pk,
                    "invitee_email": invitee_email,
                }
            )
            invite_url = request.build_absolute_uri(
                reverse("imperial_coldfront_plugin:accept_group_invite", args=[token])
            )
            send_group_invite_email(invitee_email, group.owner, invite_url, expiration)
            return render(
                request,
                "imperial_coldfront_plugin/invite_sent.html",
                dict(invitee_email=invitee_email, group_pk=group_pk),
            )
    return HttpResponseBadRequest("Invalid data")


@login_required
def accept_group_invite(request: HttpRequest, token: str) -> HttpResponse:
    """Accept invitation to a group.

    Args:
        request: The HTTP request object containing metadata about the request.
        token: The token that was sent to the invitee.
    """
    signer = TimestampSigner()

    # Validate token.
    try:
        invite = signer.unsign_object(token, max_age=settings.INVITATION_TOKEN_TIMEOUT)
    except SignatureExpired:
        return HttpResponseBadRequest("Expired token")
    except BadSignature:
        return HttpResponseBadRequest("Bad token")

    # Check the correct user is using the token.
    if invite["invitee_email"] != request.user.email:
        return HttpResponseForbidden(
            "The invite token is not associated with this email address."
        )

    group = ResearchGroup.objects.get(pk=invite["group_pk"])
    expiration = timezone.datetime.fromisoformat(invite["expiration"])

    if request.method == "POST":
        form = TermsAndConditionsForm(request.POST)
        # Check if the user has accepted the terms and conditions.
        if form.is_valid():
            # Update group membership in the database.
            try:
                GroupMembership.objects.create(
                    group=group,
                    member=request.user,
                    expiration=expiration,
                )
            except IntegrityError:
                return HttpResponseBadRequest("User already in group")
            send_group_access_granted_email(request.user, group.owner)
            return render(
                request=request,
                template_name="imperial_coldfront_plugin/accept_group_invite.html",
                context={
                    "inviter": group.owner,
                    "group": group.name,
                    "expiration": expiration,
                },
            )
    else:
        form = TermsAndConditionsForm()
    return render(
        request=request,
        context={
            "inviter": group.owner,
            "group": group.name,
            "expiration": expiration,
            "form": form,
        },
        template_name="imperial_coldfront_plugin/member_terms_and_conditions.html",
    )


@login_required
def remove_group_member(request: HttpRequest, group_membership_pk: int) -> HttpResponse:
    """Remove a member from a research group.

    Returns:
        HttpResponse: Redirects to the group members view.
    """
    group_membership = get_object_or_404(GroupMembership, pk=group_membership_pk)
    group = group_membership.group
    check_group_owner_manager_or_superuser(group, request.user)

    if group_membership.member == request.user:
        return HttpResponseForbidden("You cannot remove yourself from the group.")

    group_membership.delete()

    return redirect(reverse("imperial_coldfront_plugin:group_members", args=[group.pk]))


def get_group_data(request: HttpRequest) -> HttpResponse:
    """Get the group data in unix etc/group format.

    Args:
        request: The HTTP request object containing metadata about the request.
    """
    groups = ""
    format_str = "{group.name}:x:{group.gid}:{users}\n"
    qs = ResearchGroup.objects.all()
    for group in qs:
        users = group.groupmembership_set.values_list("member__username", flat=True)
        groups += format_str.format(group=group, users=",".join(users))

    return HttpResponse(groups)


@login_required
def make_group_manager(request: HttpRequest, group_membership_pk: int) -> HttpResponse:
    """Make a group member a manager.

    Args:
        request: The HTTP request object containing metadata about the request.
        group_membership_pk: The primary key of the group membership to be updated.
    """
    group_membership = get_object_or_404(GroupMembership, pk=group_membership_pk)
    group = group_membership.group
    check_group_owner_or_superuser(group, request.user)

    if group_membership.expiration.date() < timezone.now().date():
        return HttpResponseBadRequest("Membership has expired.")

    group_membership.is_manager = True
    group_membership.save()

    send_member_promotion_to_manager_email(group_membership.member, group.owner)

    return redirect(reverse("imperial_coldfront_plugin:group_members", args=[group.pk]))


@login_required
def remove_group_manager(
    request: HttpRequest, group_membership_pk: int
) -> HttpResponse:
    """Remove a group manager.

    Args:
        request: The HTTP request object containing metadata about the request.
        group_membership_pk: The primary key of the group membership to be updated.
    """
    group_membership = get_object_or_404(GroupMembership, pk=group_membership_pk)
    group = group_membership.group
    check_group_owner_or_superuser(group, request.user)

    group_membership.is_manager = False
    group_membership.save()

    send_manager_removed_email(group_membership.member, group.owner)

    return redirect(reverse("imperial_coldfront_plugin:group_members", args=[group.pk]))


@login_required
def group_membership_extend(
    request: HttpRequest, group_membership_pk: int
) -> HttpResponse:
    """Extend the membership of a group member.

    Args:
        request: The HTTP request object containing metadata about the request.
        group_membership_pk: The primary key of the group membership to be updated.
    """
    group_membership = get_object_or_404(GroupMembership, pk=group_membership_pk)
    group = group_membership.group

    check_group_owner_manager_or_superuser(group, request.user)

    if group_membership.member == request.user:
        return HttpResponseForbidden("You cannot extend your own membership.")

    # on GET request - display the user's information and the current expiry
    # date as well as a form allowing them to specify the length of an
    # extension.
    # on POST request - updates the expiry date of the GroupMembership based
    # on the form data and redirects to group_members_view.

    if request.method == "POST":
        form = GroupMembershipExtendForm(request.POST)
        if form.is_valid():
            extend_length = form.cleaned_data["extend_length"]
            group_membership.expiration += timedelta(days=extend_length)
            group_membership.save()
            return redirect(
                reverse("imperial_coldfront_plugin:group_members", args=[group.pk])
            )

    else:
        form = GroupMembershipExtendForm()

    return render(
        request,
        "imperial_coldfront_plugin/extend_membership.html",
        dict(form=form, group_membership=group_membership),
    )


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
            storage_size_gb = form.cleaned_data["size"]
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

            rdf_resource = Resource.objects.get(name="RDF Project Storage Space")

            allocation_active_status = AllocationStatusChoice.objects.get(name="Active")

            # We create a new user and an associated project, if they don't exist.
            user = get_or_create_user(form.cleaned_data["username"])
            project = get_or_create_project(user)

            rdf_allocation = Allocation.objects.create(
                project=project,
                status=allocation_active_status,
                quantity=1,
                start_date=timezone.now().date(),
                end_date=form.cleaned_data["end_date"],
            )
            rdf_allocation.resources.add(rdf_resource)

            storage_quota_attribute_type = AllocationAttributeType.objects.get(
                name="Storage Quota (GB)"
            )
            AllocationAttribute.objects.create(
                allocation_attribute_type=storage_quota_attribute_type,
                allocation=rdf_allocation,
                value=storage_size_gb,
            )

            AllocationAttribute.objects.create(
                allocation_attribute_type=rdf_id_attribute_type,
                allocation=rdf_allocation,
                value=project_id,
            )

            dart_id_attribute_type = AllocationAttributeType.objects.get(
                name="DART ID", is_changeable=False
            )
            AllocationAttribute.objects.create(
                allocation_attribute_type=dart_id_attribute_type,
                allocation=rdf_allocation,
                value=dart_id,
            )

            chain = Chain(cached=True)
            if settings.LDAP_ENABLED:
                chain.append(
                    "imperial_coldfront_plugin.ldap._ldap_create_group", project_id
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
                    settings.GPFS_FILESET_PATH,
                    settings.GPFS_FILESYSTEM_NAME,
                    faculty,
                )
                relative_projects_path = Path(
                    department,
                    project.pi.username,
                )

                chain.append(
                    "imperial_coldfront_plugin.gpfs_client._create_fileset_set_quota",
                    filesystem_name=settings.GPFS_FILESYSTEM_NAME,
                    owner_id="root",
                    group_id="root",
                    fileset_name=project_id,
                    parent_fileset_path=parent_fileset_path,
                    relative_projects_path=relative_projects_path,
                    permissions=settings.GPFS_PERMISSIONS,
                    block_quota=f"{storage_size_gb}G",
                    files_quota=settings.GPFS_FILES_QUOTA,
                    parent_fileset=faculty,
                )

            group = chain.run()
            messages.success(request, "RDF allocation created successfully.")
            return redirect("imperial_coldfront_plugin:list_tasks", group=group)
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
def task_stat_view(request, group: str):
    """Displays a list of tasks and their status."""
    if not request.user.is_superuser:
        return HttpResponseForbidden()

    task_qs = Task.objects.filter(group=group).order_by("started").reverse()
    return render(
        request, "imperial_coldfront_plugin/task_list.html", context={"tasks": task_qs}
    )


def get_or_create_user(username: str) -> User:
    """Get user from the database or creates one using data from Graph.

    Args:
        username: The username of the user to be retrieved or created.

    Return:
        The user, already existing or newly created.
    """
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        client = get_graph_api_client()
        user_data = client.user_profile(username)
        user = User.objects.create(
            username=user_data["username"],
            first_name=user_data["first_name"],
            last_name=user_data["last_name"],
            email=user_data["email"],
        )
    return user


def get_or_create_project(user: User) -> Project:
    """Get project from the database or creates one.

    Args:
        user: The user object that will own a project.

    Return:
        The project, already existing or newly created.
    """
    project, project_created = Project.objects.get_or_create(
        pi=user,
        title=f"{user.get_full_name()}'s Research Group",
        status=ProjectStatusChoice.objects.get(name="Active"),
    )
    if project_created:
        ProjectUser.objects.create(
            user=user,
            project=project,
            role=ProjectUserRoleChoice.objects.get_or_create(name="Manager")[0],
            status=ProjectUserStatusChoice.objects.get_or_create(name="Active")[0],
        )
    return project
