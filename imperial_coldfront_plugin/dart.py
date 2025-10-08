"""Module for creation and validation of Dart ID AllocationAttribute's.

Note that this module is not currently used by the plugin, but is provided
for anticipated future integration with DART.
"""

from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
)


class DartIDValidationError(Exception):
    """Error when a Dart ID does not meet validation criteria."""


def validate_dart_id(dart_id: str, allocation: Allocation) -> None:
    """Validate range and availability of Dart ID value.

    Args:
        dart_id (str): Dart ID to validate.
        allocation (Allocation): Allocation to check against.

    Raises:
        DartIDValidationError: If the Dart ID is not a number or is outside
            the valid range or if it is already assigned to the allocation.
    """
    try:
        if int(dart_id) < 1:
            raise DartIDValidationError("Dart ID outside valid range")
    except ValueError:
        raise DartIDValidationError("Dart ID is not a number")
    if AllocationAttribute.objects.filter(
        allocation_attribute_type__name="DART ID", value=dart_id, allocation=allocation
    ).exists():
        raise DartIDValidationError("Dart ID already assigned to this allocation")


def create_dart_id_attribute(dart_id: str, allocation: Allocation) -> Allocation:
    """Create an AllocationAttribute for a Dart ID.

    Args:
        dart_id: Dart ID to assign.
        allocation: Allocation to assign the Dart ID to.
    """
    validate_dart_id(dart_id, allocation)
    dart_id_attribute_type = AllocationAttributeType.objects.get(
        name="DART ID", is_changeable=False
    )
    return AllocationAttribute.objects.create(
        allocation_attribute_type=dart_id_attribute_type,
        allocation=allocation,
        value=dart_id,
    )
