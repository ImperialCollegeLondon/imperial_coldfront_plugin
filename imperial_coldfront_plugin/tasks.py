"""Plugin tasks."""

import datetime

import django.utils
from django.conf import settings

from .emails import send_expiration_alert_email
from .models import GroupMembership


def send_expiration_notifications():
    """Send expiration notifications to users whose memberships are about to expire."""
    expiration_days = settings.MEMBERSHIP_EXPIRATION_DAYS
    expiration_date = django.utils.timezone.now() + datetime.timedelta(
        days=expiration_days
    )
    memberships = GroupMembership.objects.filter(expiration=expiration_date)
    for membership in memberships:
        send_expiration_alert_email(membership.user, membership.group, expiration_date)
