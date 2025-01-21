"""Helper functions."""

from django.conf import settings
from django.core.mail import send_mail
from django_q.tasks import async_task


def send_email_in_background(to_addresses: list[str], subject: str, body: str):
    """Wraps Django email functionality to send emails via a Django Q task.

    Args:
        to_addresses: A list of email addresses to send the email to.
        subject: The subject of the email.
        body: The body of the email.
    """
    async_task(
        send_mail,
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        to_addresses,
        timeout=(settings.EMAIL_TIMEOUT or 0) + 1,
    )
