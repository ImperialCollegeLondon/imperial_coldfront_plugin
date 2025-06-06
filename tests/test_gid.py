import pytest

from imperial_coldfront_plugin.gid import NoGIDAvailableError, get_new_gid


def test_get_new_gid_no_existing_gids(db, settings):
    """Test when no existing GIDs are present.

    This test checks that get_new_gid returns the first GID in the range
    when no existing GIDs are present.
    """
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = [range(1000, 2000)]

    # Call the get_new_gid function
    gid = get_new_gid()

    # Assert that the returned GID is the start of the range
    assert gid == 1000


@pytest.mark.parametrize(
    "existing_gid, raised_error",
    [
        (1500, False),  # Existing GID is in the middle of the range
        (1999, True),  # Existing GID is at the end of the range
        (2000, True),  # Existing GID is outside the range
        (2001, True),  # Existing GID is outside the range
    ],
)
def test_get_new_gid(
    settings, allocation_attribute_factory, existing_gid, raised_error
):
    """Test the get_new_gid function with various existing GID scenarios.

    This test checks the behavior of get_new_gid when there are existing GIDs
    in the database, including cases where the existing GID is in the middle of
    the range, at the end of the range, or outside the configured ranges.
    """
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = [range(1000, 2000)]

    # Create an existing GID at the end of the range
    allocation_attribute_factory(name="GID", value=existing_gid)
    if raised_error:
        # Assert that NoGIDAvailableError is raised
        with pytest.raises(NoGIDAvailableError):
            get_new_gid()
    else:
        # Call the get_new_gid function
        gid = get_new_gid()
        # Assert that the returned GID is the next available GID
        assert gid == existing_gid + 1


def test_when_smaller_than_min_range(settings, allocation_attribute_factory):
    """Test when existing GID is smaller than the minimum of the range."""
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = [range(1000, 2000)]

    # Create an existing GID outside the range
    allocation_attribute_factory(name="GID", value=999)

    # Call the get_new_gid function
    gid = get_new_gid()

    # Assert that the returned GID is the start of the range
    assert gid == 1000


def test_multiple_gid_ranges(settings, allocation_attribute_factory):
    """Test when multiple GID ranges are configured."""
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = [range(1000, 1100), range(2000, 2100)]

    # Create an existing GID at the end of the first range
    allocation_attribute_factory(name="GID", value=1099)

    # Call the get_new_gid function
    gid = get_new_gid()

    # Assert that the returned GID is the start of the next range
    assert gid == 2000
