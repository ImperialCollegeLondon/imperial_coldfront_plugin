"""Template filter for calculating days until a given date."""

from datetime import timedelta

from django import template
from django.conf import settings
from django.utils import timezone

register = template.Library()


@register.filter
def days_until(allocation: object) -> int | None:
    """Calculate days until the next status change based on allocation status.

    For Expired: days until removal (end_date + REMOVAL_DAYS)
    For Removed: days until deletion (end_date + DELETION_DAYS)
    For Deleted: returns None (no countdown)
    """
    if not hasattr(allocation, "status") or not hasattr(allocation, "end_date"):
        return None

    if not allocation.end_date:
        return None

    removal_days = settings.RDF_ALLOCATION_EXPIRY_REMOVAL_DAYS
    deletion_days = settings.RDF_ALLOCATION_EXPIRY_DELETION_DAYS

    if allocation.status.name == "Expired":
        deadline = allocation.end_date + timedelta(days=removal_days)
    elif allocation.status.name == "Removed":
        deadline = allocation.end_date + timedelta(days=deletion_days)
    else:
        return None

    days = (deadline - timezone.now().date()).days
    return max(0, days)
