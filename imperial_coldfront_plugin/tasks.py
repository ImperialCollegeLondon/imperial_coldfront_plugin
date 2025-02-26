"""Plugin tasks."""

from datetime import timedelta, timezone

from django.conf import settings

from .emails import send_expiration_alert_email
from .models import GroupMembership


def send_expiration_notifications():
    """Send expiration notifications to users whose memberships are about to expire."""
    expiration_days = settings.MEMBERSHIP_EXPIRATION_DAYS
    expiration_date = timezone.now() + timedelta(days=expiration_days)
    memberships = GroupMembership.objects.filter(expiration_date=expiration_date)
    for membership in memberships:
        send_expiration_alert_email(membership.user, membership.group, expiration_date)
