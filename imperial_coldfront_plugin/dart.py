"""Module for creation and validation of Dart ID AllocationAttribute's."""

from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
)


class DartIDValidationError(Exception):
    """Error when a Dart ID does not meet validation criteria."""


def validate_dart_id(dart_id: str, allocation: Allocation):
    """Validate range and availability of Dart ID value."""
    try:
        if int(dart_id) < 1:
            raise DartIDValidationError("Dart ID outside valid range")
    except ValueError:
        raise DartIDValidationError("Dart ID is not a number")
    if AllocationAttribute.objects.filter(
        allocation_attribute_type__name="DART ID", value=dart_id, allocation=allocation
    ).exists():
        raise DartIDValidationError("Dart ID already assigned to this allocation")


def create_dart_id_attribute(dart_id: str, allocation: Allocation):
    """Create an AllocationAttribute for a Dart ID."""
    validate_dart_id(dart_id, allocation)
    dart_id_attribute_type = AllocationAttributeType.objects.get(
        name="DART ID", is_changeable=False
    )
    return AllocationAttribute.objects.create(
        allocation_attribute_type=dart_id_attribute_type,
        allocation=allocation,
        value=dart_id,
    )
