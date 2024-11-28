"""Plugin views."""

from django.conf import settings
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.urls import reverse


def invite_to_group(request: HttpRequest) -> HttpResponse:
    """Add an individual to a group."""
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
    """Accept invitation to a group."""
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
