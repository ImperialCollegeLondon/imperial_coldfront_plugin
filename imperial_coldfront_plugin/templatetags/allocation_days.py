"""Template filter for calculating days until a given date."""

from datetime import date

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def days_until(date_value: date) -> int | None:
    """Calculate days until the given date from today."""
    if date_value:
        days = (date_value - timezone.now().date()).days
        return max(0, days)
    return None
