import pytest
from django.core.exceptions import ImproperlyConfigured

from imperial_coldfront_plugin.settings_validation import validate_schedules


def test_validate_schedules_valid():
    """Test validate_schedules with valid schedules."""
    validate_schedules([5, 3, 1], [0, -1, -2], [-3, -4, -5], [-6, -7, -8])


@pytest.mark.parametrize("value", (0, -1))
def test_validate_schedules_positive_integers(value):
    """Test validate_schedules with invalid schedules."""
    with pytest.raises(
        ImproperlyConfigured,
        match=(
            "RDF_ALLOCATION_EXPIRY_WARNING_SCHEDULE must contain only positive integers"
        ),
    ):
        validate_schedules([value, -2, -3], [-4, -5, -6], [-7, -8, -9], [-10, -11, -12])


def test_validate_schedule_non_positive_integers():
    """Test validate_schedules with invalid schedules."""
    with pytest.raises(
        ImproperlyConfigured,
        match=(
            "RDF_ALLOCATION_REMOVAL_WARNING_SCHEDULE must contain only non-positive "
            "integers"
        ),
    ):
        validate_schedules([5, 4, 3], [1, 0, -2], [-3, -4, -5], [-6, -7, -8])


def test_validate_schedule_overlap():
    """Test validate_schedules with overlapping schedules."""
    with pytest.raises(
        ImproperlyConfigured,
        match="Misconfiguration detected in RDF allocation notification schedule",
    ):
        validate_schedules([5, 4, 3], [0, -1, -3], [-2, -4, -5], [-6, -7, -8])


def test_validate_schedule_out_of_sequence():
    """Test validate_schedules with mis-ordered schedules."""
    with pytest.raises(
        ImproperlyConfigured,
        match="Misconfiguration detected in RDF allocation notification schedule",
    ):
        validate_schedules([5, 4, 3], [-3, -4, -5], [0, -1, -2], [-6, -7, -8])
