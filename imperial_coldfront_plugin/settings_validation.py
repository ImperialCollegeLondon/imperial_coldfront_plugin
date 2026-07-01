"""Helpers for validating settings in the Imperial Coldfront plugin."""

from itertools import pairwise

from django.core.exceptions import ImproperlyConfigured


def validate_schedules(
    expiry_warning_schedule: list[int],
    removal_warning_schedule: list[int],
    deletion_warning_schedule: list[int],
    deletion_notification_schedule: list[int],
) -> None:
    """Validate the notification schedules for RDF allocations.

    Args:
        expiry_warning_schedule: days before expiry to send expiry warnings.
        removal_warning_schedule: days after to expiry to send removal warnings.
        deletion_warning_schedule: days after expiry to send deletion warnings.
        deletion_notification_schedule: days after expiry to send notifications.

    Raises:
        ImproperlyConfigured: If any of the schedules are misconfigured.
    """
    if any(val < 1 for val in expiry_warning_schedule):
        raise ImproperlyConfigured(
            "RDF_ALLOCATION_EXPIRY_WARNING_SCHEDULE must contain only positive integers"
        )

    if any(val > 0 for val in removal_warning_schedule):
        raise ImproperlyConfigured(
            "RDF_ALLOCATION_REMOVAL_WARNING_SCHEDULE must contain only non-positive "
            "integers"
        )

    for schedule1, schedule2 in pairwise(
        (
            expiry_warning_schedule,
            removal_warning_schedule,
            deletion_warning_schedule,
            deletion_notification_schedule,
        )
    ):
        if max(schedule2) >= min(schedule1):
            raise ImproperlyConfigured(
                "Misconfiguration detected in RDF allocation notification schedule. "
                "Schedules must be correctly sequenced and non-overlapping."
            )
