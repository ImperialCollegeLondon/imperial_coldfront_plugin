"""Utility functions for the Imperial Coldfront plugin."""

from coldfront.core.allocation.models import AllocationAttribute


def get_allocation_shortname(allocation):
    """Get the shortname attribute for an allocation."""
    try:
        return allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Shortname"
        ).value
    except (
        AllocationAttribute.MultipleObjectsReturned,
        AllocationAttribute.DoesNotExist,
    ):
        return ""
