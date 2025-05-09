"""Functionality to get a new GID value."""

from coldfront.core.allocation.models import AllocationAttribute
from django.conf import settings


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
    existing_gids = AllocationAttribute.objects.filter(
        allocation_attribute_type__name="GID"
    )

    # Get the maximum GID value already assigned
    try:
        max_gid = max(eg.typed_value() for eg in existing_gids)
    except ValueError:
        # if there are no existing gids
        max_gid = None

    # Check each range to find the first available GID
    for gid_range in settings.GID_RANGES:
        start = gid_range.start
        end = gid_range.stop
        if max_gid is None or max_gid < start:
            return start

        if max_gid < end:
            return max_gid + 1

    raise ValueError("No available GID found in the configured ranges.")
