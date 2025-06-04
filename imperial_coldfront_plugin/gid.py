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
    """
    existing_gids = AllocationAttribute.objects.filter(
        allocation_attribute_type__name="GID"
    )

    max_gid = max(eg.typed_value() for eg in existing_gids)

    # Check each range to find the first available GID
    for index, range in enumerate(settings.GID_RANGES):
        if max_gid in range:
            if max_gid != range[-1]:  # If max_gid is not the last in the range
                return max_gid + 1
            else:
                if index + 1 < len(
                    settings.GID_RANGES
                ):  # if at the end of the range, get the next range
                    return settings.GID_RANGES[index + 1][0]
                else:
                    raise ValueError(
                        f"{max_gid} is the last of available \
                    GIDs in the specified ranges."
                    )
    raise ValueError(f"{max_gid} is outside all the specified ranges.")
