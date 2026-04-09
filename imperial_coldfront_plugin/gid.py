"""Functionality to get a new GID value."""

from itertools import pairwise

from coldfront.core.allocation.models import AllocationAttribute
from django.conf import settings

# these values are deliberately hardcoded according to the gid range we have been
# assigned changing them is meant to be a pain and must only be carried out in
# agreement with the identity management team.
# Something more sophisticated will be needed if we ever have multiple ranges
ALLOWED_GID_RANGES = [range(881436, 1031436)]


class NoGIDAvailableError(Exception):
    """Error when no available GID found in the configured ranges."""


def get_new_gid(range_name: str) -> int:
    """Get a new GID value.

    This function checks the existing GID values in the database and returns
    the next available GID within the specified ranges. If no GID is
    available, it raises a ValueError.

    Arguments:
        range_name: The name of the GID range to use (e.g., "hx2" or "rdf").

    Returns:
        int: The next available GID value.
    """
    existing_gids = AllocationAttribute.objects.filter(
        allocation_attribute_type__name="GID"
    )

    gid_ranges = settings.GID_RANGES[range_name]
    range_limits = gid_ranges[0].start, gid_ranges[-1].stop + 1

    # Get the maximum GID value already assigned in the selected_range
    try:
        max_gid = max(
            (
                val
                if range_limits[0] <= (val := eg.typed_value()) <= range_limits[1]
                else 0
            )
            for eg in existing_gids
        )
    except ValueError:
        # if there are no existing gids
        max_gid = None

    # Check each range to find the first available GID
    for index, range in enumerate(gid_ranges):
        if max_gid is None or max_gid < range[0]:
            # If no existing GIDs, return the first GID in the range
            return range[0]

        elif max_gid in range:
            if max_gid != range[-1]:  # If max_gid is not the last in the range
                return max_gid + 1
            else:
                if index + 1 < len(
                    gid_ranges
                ):  # if at the end of the range, get the next range
                    return gid_ranges[index + 1][0]
    raise NoGIDAvailableError("No available GID found in the configured ranges.")


def validate_gid_ranges(ranges: list[range]) -> None:
    """Validate the GID ranges.

    This function checks that the provided GID ranges are valid, i.e., they do not
     overlap and are in ascending order.

    Args:
        ranges: GID ranges to validate.

    Raises:
        ValueError: If the ranges are not valid.
    """
    for r in ranges:
        if all(r.start not in allowed_range for allowed_range in ALLOWED_GID_RANGES):
            raise ValueError(f"GID range start {r.start} is outside of allowed range.")
        if all(r.stop - 1 not in allowed_range for allowed_range in ALLOWED_GID_RANGES):
            raise ValueError(f"GID range end {r.stop - 1} is outside of allowed range.")
        if r.stop < r.start:
            raise ValueError(f"GID range end {r.stop} is less than start {r.start}.")
        if r.step != 1:
            raise ValueError(f"GID range step must be 1, got {r.step}.")

    for r1, r2 in pairwise(ranges):
        if r1.stop > r2.start:
            raise ValueError("GID ranges must not overlap and be in ascending order.")


def validate_gid_range_overlap(ranges_by_type: dict[str, list[range]]) -> None:
    """Validate that GID ranges across different named types do not overlap.

    Args:
        ranges_by_type: Mapping of range name -> list of validated ranges.

    Raises:
        ValueError: If any ranges overlap between different range names.
    """
    entries: list[range] = [r for ranges in ranges_by_type.values() for r in ranges]
    # Sort by start so we only have to check adjacent intervals for overlap
    entries.sort(key=lambda r: r.start)

    for r1, r2 in pairwise(entries):
        if r1.stop > r2.start:
            raise ValueError(
                "Overlapping GID ranges detected between different range names."
            )
