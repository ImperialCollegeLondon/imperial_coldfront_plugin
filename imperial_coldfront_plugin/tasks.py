"""Plugin tasks."""

import datetime
from functools import wraps

from django.conf import settings
from django_q.tasks import async_task, schedule

from .emails import send_expiration_alert_email
from .models import GroupMembership


def send_expiration_notifications():
    """Notify members of upcoming group membership expirations."""
    notification_days = settings.EXPIRATION_NOTIFICATION_DAYS

    for delta_days in notification_days:
        for membership in GroupMembership.objects.filter(
            expiration=datetime.date.today() + datetime.timedelta(days=delta_days)
        ):
            group = membership.group

            send_expiration_alert_email(
                membership.member, group.owner, membership.expiration
            )


def run_in_background(func):
    """Wrapper to run a function.

    Note that Django q's architecture means this can't be used as a straight decorator
    and it's output must be stored as a different name from the wrapped function.
    """

    @wraps(func)
    def wrapped(*args, **kwargs):
        return async_task(func, *args, **kwargs)

    return wrapped


def run_consistency_check():
    """Run the LDAP consistency check task."""
    # Schedule the task to run daily
    schedule(
        "imperial_coldfront_plugin.ldap.check_ldap_consistency",
        schedule_type="D",
        repeats=-1,
        next_run=datetime.datetime.now(),
    )
