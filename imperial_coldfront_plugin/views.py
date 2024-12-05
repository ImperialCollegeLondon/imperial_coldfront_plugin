"""Plugin views."""

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

from .forms import GroupMembershipForm
from .models import GroupMembership, ResearchGroup

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


@login_required
def send_group_invite(request: HttpRequest) -> HttpResponse:
    """Invite an individual to a group."""
    if request.method == "POST":
        form = GroupMembershipForm(request.POST)

        if form.is_valid():
            invitee_email = form.cleaned_data["invitee_email"]

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

            # Send invitation via email.
            send_mail(
                "You've been invited to a group",
                f"Click the following link to accept the invitation:\n{invite_url}",
                request.user.email,
                [invitee_email],
            )

    else:
        form = GroupMembershipForm()

    return render(
        request,
        "imperial_coldfront_plugin/send_group_invite.html",
        {"form": form},
    )


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
        invite = signer.unsign_object(token, max_age=86400)
    except SignatureExpired:
        return HttpResponseBadRequest("Expired token")
    except BadSignature:
        return HttpResponseBadRequest("Bad token")

    # Check the correct user is using the token.
    if invite["invitee_email"] != request.user.email:
        return HttpResponseForbidden(
            "The invite token is not associated with this email address."
        )

    # Update group membership in the database.
    group = ResearchGroup.objects.get(owner__pk=invite["inviter_pk"])
    GroupMembership.objects.create(group=group, member=request.user)

    return render(
        request=request,
        context={
            "inviter_pk": invite["inviter_pk"],
            "invitee_email": invite["invitee_email"],
        },
        template_name="imperial_coldfront_plugin/accept_group_invite.html",
    )


@login_required
def index(request: HttpRequest) -> HttpResponse:
    """Render the index page.

    Args:
        request: The HTTP request object containing metadata about the request.
    """
    return render(request, "imperial_coldfront_plugin/index.html")
