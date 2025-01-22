"""Plugin views."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import GroupMembershipForm, TermsAndConditionsForm, UserSearchForm
from .microsoft_graph_client import get_graph_api_client
from .models import GroupMembership, ResearchGroup
from .policy import user_eligible_for_hpc_access
from .utils import send_email_in_background

User = get_user_model()


@login_required
def group_members_view(request: HttpRequest, user_pk: int) -> HttpResponse:
    """Display the members of a research group for a specific user.

    This view retrieves and displays all members associated with a research group
    where the specified user (identified by `user_pk`) is the owner. Access is
    restricted to either the group owner, an administrator, or a manager.
    Unauthorised users will receive a permission denied response.

    The view also checks if the specified user has Principal Investigator (PI) status
    (via the `is_pi` attribute). If the user is not a PI, the view will render a
    message indicating that the user does not own a group.

    Args:
        request (HttpRequest): The HTTP request object containing metadata about the
            request.
        user_pk (int): The primary key of the user who owns the research group to be
            displayed.

    Returns:
        HttpResponse: If access is permitted, renders `group_members.html`
                      displaying the group members.
                      If the logged-in user is unauthorised, returns a
                      `HttpResponseForbidden`.
                      If the user is not a PI, renders `no_group.html` with an
                      appropriate message.

    Raises:
        Http404: If no user is found with the provided `user_pk`.
    """
    user = get_object_or_404(User, pk=user_pk)

    if request.user != user and not request.user.is_superuser:
        return HttpResponseForbidden("Permission denied")

    if not user.userprofile.is_pi:
        return render(request, "no_group.html", {"message": "You do not own a group."})

    group_members = GroupMembership.objects.filter(group__owner=user)
    return render(request, "group_members.html", {"group_members": group_members})


@login_required
def check_access(request: HttpRequest):
    """Informational view displaying the user's current access to RCS resources."""
    if request.user.userprofile.is_pi:
        message = "You have access to RCS resources as a PI."
    elif request.user.is_superuser:
        message = "You have access to RCS resources as an administrator."
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
def user_search(request: HttpRequest) -> HttpResponse:
    """Simple search interface to find users eligible to join a ResearchGroup."""
    if request.method == "POST":
        form = UserSearchForm(request.POST)
        if form.is_valid():
            search_query = form.cleaned_data["search"]
            graph_client = get_graph_api_client()
            search_results = graph_client.user_search(search_query)
            filtered_results = [
                user for user in search_results if user_eligible_for_hpc_access(user)
            ]
            return render(
                request,
                "imperial_coldfront_plugin/user_search.html",
                dict(form=form, search_results=filtered_results),
            )
    else:
        form = UserSearchForm()

    return render(
        request, "imperial_coldfront_plugin/user_search.html", dict(form=form)
    )


@login_required
def send_group_invite(request: HttpRequest) -> HttpResponse:
    """Invite an individual to a group."""
    if (
        not ResearchGroup.objects.filter(owner=request.user).exists()
        and not GroupMembership.objects.filter(
            member=request.user, is_manager=True
        ).exists()
    ):
        return HttpResponseForbidden("You are not a group owner.")

    if request.method == "POST":
        form = GroupMembershipForm(request.POST)

        if form.is_valid():
            username = form.cleaned_data["username"]
            graph_client = get_graph_api_client()
            user_profile = graph_client.user_profile(username)

            if not user_eligible_for_hpc_access(user_profile):
                return HttpResponseBadRequest("User not found or not eligible")

            invitee_email = user_profile["email"]

            # Create invitation URL.
            signer = TimestampSigner()
            token = signer.sign_object(
                {
                    "inviter_pk": request.user.pk,
                    "invitee_email": invitee_email,
                }
            )
            invite_url = request.build_absolute_uri(
                reverse("imperial_coldfront_plugin:accept_group_invite", args=[token])
            )
            send_email_in_background(
                [invitee_email],
                "HPC Access Invitation",
                "You've been invited to join the access group of "
                f"{request.user.get_full_name()} ({request.user.email})\n\n"
                f"Click the following link to accept the invitation:\n{invite_url}",
            )
            return render(
                request,
                "imperial_coldfront_plugin/invite_sent.html",
                dict(invitee_email=invitee_email),
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

    group = ResearchGroup.objects.get(owner__pk=invite["inviter_pk"])

    if request.method == "POST":
        form = TermsAndConditionsForm(request.POST)
        # Check if the user has accepted the terms and conditions.
        if form.is_valid():
            # Update group membership in the database.
            GroupMembership.objects.get_or_create(group=group, member=request.user)
            return render(
                request=request,
                template_name="imperial_coldfront_plugin/accept_group_invite.html",
                context={"inviter": group.owner, "group": group.name},
            )
    else:
        form = TermsAndConditionsForm()
    return render(
        request=request,
        context={"inviter": group.owner, "group": group.name, "form": form},
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

    if (
        request.user != group.owner
        and not request.user.is_superuser
        and not GroupMembership.objects.filter(
            group=group, member=request.user, is_manager=True
        ).exists()
    ):
        return HttpResponseForbidden("Permission denied")

    if group_membership.member == request.user:
        return HttpResponseForbidden("You cannot remove yourself from the group.")

    group_membership.delete()

    return redirect(
        reverse("imperial_coldfront_plugin:group_members", args=[group.owner.pk])
    )


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
            user=user, uid=user.unixuid, group=user.groupmembership_set.get().group
        )
    for user in (
        User.objects.filter(userprofile__is_pi=True)
        .filter(unixuid__isnull=False)
        .distinct()
        .difference(qs)
    ):
        passwd += format_str.format(
            user=user, uid=user.unixuid, group=user.researchgroup_set.get()
        )

    return HttpResponse(passwd)


@login_required
def make_group_manager(request: HttpRequest, group_membership_pk: int) -> HttpResponse:
    """Make a group member a manager.

    Args:
        request: The HTTP request object containing metadata about the request.
        group_membership_pk: The primary key of the group membership to be updated.
    """
    group_membership = get_object_or_404(GroupMembership, pk=group_membership_pk)
    group = group_membership.group

    if (
        request.user != group.owner
        and not request.user.is_superuser
        and not GroupMembership.objects.filter(
            group=group, member=request.user, is_manager=True
        ).exists()
    ):
        return HttpResponseForbidden("Permission denied")

    group_membership.is_manager = True
    group_membership.save()

    return redirect(
        reverse("imperial_coldfront_plugin:group_members", args=[group.owner.pk])
    )


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

    if (
        request.user != group.owner
        and not request.user.is_superuser
        and not GroupMembership.objects.filter(
            group=group, member=request.user, is_manager=True
        ).exists()
    ):
        return HttpResponseForbidden("Permission denied")

    group_membership.is_manager = False
    group_membership.save()

    return redirect(
        reverse("imperial_coldfront_plugin:group_members", args=[group.owner.pk])
    )
