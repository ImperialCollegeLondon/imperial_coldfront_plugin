"""Plugin views."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .models import GroupMembership

User = get_user_model()


@login_required
def group_members_view(request: HttpRequest, user_pk: int) -> HttpResponse:
    """Display the members of a research group for a specific user.

    This view retrieves and displays all members associated with a research group
    where the specified user (identified by `user_pk`) is the owner. Access is
    restricted to either the group owner or an administrator. Unauthorised users will
    receive a permission denied response.

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

    group_members = GroupMembership.objects.filter(owner=user)

    return render(request, "group_members.html", {"group_members": group_members})


def invite_to_group(request: HttpRequest) -> HttpResponse:
    """Add an individual to a group.

    Args:
        request: The HTTP request object containing metadata about the request.
    """
    signer = TimestampSigner()

    # TODO: Get invitee email from request.
    invitee_email = "my@email.org"

    # Sign invitation.
    token = signer.sign_object(
        {
            "inviter_pk": request.user.pk,
            "invitee_email": invitee_email,
        }
    )

    # Send invitation via email.
    # TODO: get_host does not include protocol -- need an automagic way to get it.
    invite_url = "http://" + request.get_host() + reverse("accept_invite", args=[token])
    send_mail(
        "You've been invited to a group",
        f"Click the following link to accept the invitation: {invite_url}",
        settings.DEFAULT_FROM_EMAIL,
        [invitee_email],
    )

    return render(
        request=request,
        context={"token": token, "invite_url": invite_url},
        template_name="imperial_coldfront_plugin/invite_to_group.html",
    )


def accept_invite(request: HttpRequest, token: str) -> HttpResponse:
    """Accept invitation to a group.

    Args:
        request: The HTTP request object containing metadata about the request.
        token: The token that was sent to the invitee.
    """
    signer = TimestampSigner()

    # Validate token.
    try:
        invite = signer.unsign_object(token, max_age=86400)
    except SignatureExpired:
        return HttpResponseBadRequest("Expired token")
    except BadSignature:
        return HttpResponseBadRequest("Bad token")

    return render(
        request=request,
        context={"invite": invite},
        template_name="imperial_coldfront_plugin/accept_invite.html",
    )
