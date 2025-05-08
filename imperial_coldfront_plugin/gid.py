"""Functionality to get a new GID value."""

from coldfront.core.allocation.models import Allocation
from django.db.models import Max
from settings import GID_RANGES


def get_new_gid() -> int:
    """Get a new GID value.

    This function checks the existing GID values in the database and returns
    the next available GID within the specified ranges. If no GID is
    available, it raises a ValueError.

    Returns:
        int: The next available GID value.

    Raises:
        ValueError: If no available GID is found in the configured ranges.
    """
    existing_gids = Allocation.objects.filter(
        allocationattribute__allocation_attribute_type__name="GID"
    ).values_list("allocationattribute__value", flat=True)

    # Get the maximum GID value already assigned
    max_gid = existing_gids.aggregate(Max("allocationattribute__value"))[
        "allocationattribute__value__max"
    ]

    # Check each range to find the first available GID
    for gid_range in GID_RANGES:
        start, end = gid_range
        if max_gid is None or max_gid < start:
            return start

        if max_gid < end:
            return max_gid + 1

    raise ValueError("No available GID found in the configured ranges.")
