"""Plugin views."""

import datetime

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

from .emails import (
    send_group_access_granted_email,
    send_group_invite_email,
    send_manager_removed_email,
    send_member_promotion_to_manager_email,
)
from .forms import (
    GroupMembershipExtendForm,
    GroupMembershipForm,
    TermsAndConditionsForm,
    UserSearchForm,
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

            # If the group already exist, we just use that one
            if (query := ResearchGroup.objects.filter(owner=request.user)).exists():
                group = query.first()
                messages.success(
                    request,
                    f"A research group owned by '{request.user}' already exist.",
                )
            else:
                gid = generate_unique_gid()
                group = ResearchGroup.objects.create(
                    owner=request.user, gid=gid, name=group_name
                )
                messages.success(request, "Research group created successfully.")

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

    return render(
        request,
        "group_members.html",
        {
            "group_members": group_members,
            "is_manager": is_manager,
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
            graph_client = get_graph_api_client()
            search_results = graph_client.user_search(search_query)

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


def get_active_users(request: HttpRequest) -> HttpResponse:
    """Get the active users in unix passwd format.

    Note: the UnixUID must exist for each user in a group and the group owner, this view
    ignores users that do not have a UnixUID.

    Args:
        request: The HTTP request object containing metadata about the request.
    """
    passwd = ""
    format_str = (
        "{user.username}:x:{uid.identifier}:{group.gid}:{user.first_name} "
        "{user.last_name}:/rds/general/user/{user.username}/home:/bin/bash\n"
    )
    qs = (
        User.objects.filter(groupmembership__isnull=False)
        .filter(unixuid__isnull=False)
        .distinct()
    )
    for user in qs:
        passwd += format_str.format(
            user=user, uid=user.unixuid, group=user.groupmembership.group
        )
    for user in (
        User.objects.filter(researchgroup__isnull=False)
        .filter(unixuid__isnull=False)
        .distinct()
        .difference(qs)
    ):
        passwd += format_str.format(
            user=user, uid=user.unixuid, group=user.researchgroup_set.get()
        )

    return HttpResponse(passwd)


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
            group_membership.expiration += datetime.timedelta(days=extend_length)
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
