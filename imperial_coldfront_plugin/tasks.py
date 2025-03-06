"""Plugin tasks."""

import datetime

from dateutil.relativedelta import relativedelta
from django.conf import settings

from .emails import send_expiration_alert_email
from .models import GroupMembership


def send_expiration_notifications():
    """Send expiration notifications to users whose memberships are about to expire."""
    notification_days = settings.EXPIRATION_NOTIFICATION_DAYS

    for delta_days in notification_days:
        for membership in GroupMembership.objects.filter(
            expiration=datetime.date.today() + relativedelta(days=delta_days)
        ):
            send_expiration_alert_email(
                membership.user, membership.group, membership.expiration
            )
