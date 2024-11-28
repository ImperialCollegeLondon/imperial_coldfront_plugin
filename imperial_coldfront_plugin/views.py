"""Plugin views."""

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render


def invite_to_group(request: HttpRequest) -> HttpResponse:
    """Add an individual to a group."""
    signer = TimestampSigner()

    invite = {
        "inviter_pk": request.user.pk,
        "invitee_email": "my@email.org",
    }

    token = signer.sign_object(invite)

    import logging

    logger = logging.getLogger("django")
    logger.info(f"invite: {invite}")
    logger.info(f"token: {token}")

    return render(
        request=request, template_name="imperial_coldfront_plugin/invite_to_group.html"
    )


def accept_invite(request: HttpRequest, token: str) -> HttpResponse:
    """Accept invitation to a group."""
    signer = TimestampSigner()

    try:
        original = signer.unsign_object(token, max_age=86400)
    except SignatureExpired:
        return HttpResponseBadRequest("Token expired")
    except BadSignature:
        return HttpResponseBadRequest("Bad token")

    import logging

    logger = logging.getLogger("django")
    logger.info(f"original: {original}")

    return render(
        request=request,
        template_name="imperial_coldfront_plugin/accept_invite.html",
    )
