"""Functionality to get a new GID value."""

from coldfront.core.allocation.models import AllocationAttribute
from django.conf import settings


class NoGIDAvailableError(Exception):
    """Error when no available GID found in the configured ranges."""


def get_new_gid() -> int:
    """Get a new GID value.

    This function checks the existing GID values in the database and returns
    the next available GID within the specified ranges. If no GID is
    available, it raises a ValueError.

    Returns:
        int: The next available GID value.
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
    for index, range in enumerate(settings.GID_RANGES):
        if max_gid is None or max_gid < range[0]:
            # If no existing GIDs, return the first GID in the range
            return range[0]

        elif max_gid in range:
            if max_gid != range[-1]:  # If max_gid is not the last in the range
                return max_gid + 1
            else:
                if index + 1 < len(
                    settings.GID_RANGES
                ):  # if at the end of the range, get the next range
                    return settings.GID_RANGES[index + 1][0]
    raise NoGIDAvailableError("No available GID found in the configured ranges.")
