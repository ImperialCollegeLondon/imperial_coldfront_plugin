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
from django.views.decorators.http import require_POST

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


@require_POST
@login_required
def invite_to_group(request: HttpRequest) -> HttpResponse:
    """Invite an individual to a group.

    Args:
        request: The HTTP request object containing metadata about the request.
    """
    signer = TimestampSigner()
    invitee_email = request.POST.get("invitee_email")

    # Sign invitation.
    token = signer.sign_object(
        {
            "inviter_pk": request.user.pk,
            "invitee_email": invitee_email,
        }
    )

    invite_url = request.build_absolute_uri(
        reverse("imperial_coldfront_plugin:accept_invite", args=[token])
    )

    # Send invitation via email.
    send_mail(
        "You've been invited to a group",
        f"Click the following link to accept the invitation: {invite_url}",
        settings.DEFAULT_FROM_EMAIL,
        [invitee_email],
    )

    return render(
        request=request,
        context={
            "invitee_email": invitee_email,
            "token": token,
            "invite_url": invite_url,
        },
        template_name="imperial_coldfront_plugin/invite_to_group.html",
    )


@login_required
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

    # Check the correct user is using the token.
    if invite["invitee_email"] != request.user.email:
        return HttpResponseForbidden("This token is not for you")

    return render(
        request=request,
        context={
            "inviter_pk": invite["inviter_pk"],
            "invitee_email": invite["invitee_email"],
        },
        template_name="imperial_coldfront_plugin/accept_invite.html",
    )


def index(request: HttpRequest) -> HttpResponse:
    """Render the index page.

    Args:
        request: The HTTP request object containing metadata about the request.
    """
    return render(request=request, template_name="imperial_coldfront_plugin/index.html")
