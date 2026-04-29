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


def _get_max_gid_in_range(
    existing_gids: list[AllocationAttribute], gid_range: range
) -> int | None:
    max_gid = None
    # Get the maximum GID value already assigned in the selected_range
    try:
        max_gid = max(
            (
                val
                if gid_range.start <= (val := eg.typed_value()) < gid_range.stop
                else 0
            )
            for eg in existing_gids
        )
    except ValueError:
        # if there are no existing gids
        max_gid = None
    return max_gid or None


def get_new_gid(range_name: str) -> int:
    """Get a new GID value.

    This function checks the existing GID values in the database and returns
    the next available GID within the specified ranges. If no GID is
    available, it raises a NoGIDAvailableError.

    Arguments:
        range_name: The name of the GID range to use (e.g., "hx2" or "rdf").

    Returns:
        int: The next available GID value.
    """
    gid_ranges = settings.GID_RANGES[range_name]
    existing_gids = AllocationAttribute.objects.filter(
        allocation_attribute_type__name="GID"
    )
    for gid_range in gid_ranges:
        max_gid = _get_max_gid_in_range(existing_gids, gid_range)
        if max_gid is None:
            # If no existing GIDs, return the first GID in the range
            return gid_range[0]
        elif max_gid == gid_range.stop - 1:
            # If max_gid is at the end of the range, continue to the next range
            continue
        else:
            # If max_gid is within the range and not at the end, return the next GID
            return max_gid + 1
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
