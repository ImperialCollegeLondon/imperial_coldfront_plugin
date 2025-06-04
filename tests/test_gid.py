import pytest

from imperial_coldfront_plugin.gid import get_new_gid


@pytest.mark.django_db
def test_get_new_gid_no_existing_gids(settings):
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


@pytest.mark.django_db
def test_get_new_gid_existing_gids(settings, allocation_attribute_factory):
    """Test when existing GIDs are present.

    This test checks that get_new_gid returns the next available GID
    after the maximum existing GID.
    """
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = [range(1000, 2000)]

    # Create an existing GID in the database
    allocation_attribute_factory(allocation_attribute_type=None, value=1500)

    # Call the get_new_gid function
    gid = get_new_gid()

    # Assert that the returned GID is the next available GID
    assert gid == 1501


@pytest.mark.django_db
def test_get_new_gid_max_gid_in_range(settings, allocation_attribute_factory):
    """Test when the maximum GID is at the end of the range.

    This test checks that get_new_gid returns the next GID after the maximum
    existing GID is one less than the end of the range.
    """
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = [range(1000, 2000)]

    # Create an existing GID at the end of the range
    allocation_attribute_factory(allocation_attribute_type=None, value=1999)

    # Call the get_new_gid function and expect a ValueError
    with pytest.raises(
        ValueError, match="1999 is the last available GID in the specified ranges."
    ):
        get_new_gid()


@pytest.mark.django_db
def test_when_equal_to_max_range(settings, allocation_attribute_factory):
    """Test when existing GID is equal to the maximum of the range."""
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = [range(1000, 2000)]

    # Create an existing GID outside the range
    allocation_attribute_factory(allocation_attribute_type=None, value=2000)

    # Call the get_new_gid function and expect a ValueError
    with pytest.raises(ValueError, match="2000 is outside all the specified ranges."):
        get_new_gid()


@pytest.mark.django_db
def test_when_greater_than_max_range(settings, allocation_attribute_factory):
    """Test when existing GID is greater than the maximum of the range."""
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = [range(1000, 2000)]

    # Create an existing GID outside the range
    allocation_attribute_factory(allocation_attribute_type=None, value=2001)

    # Call the get_new_gid function and expect a ValueError
    with pytest.raises(ValueError, match="2001 is outside all the specified ranges."):
        get_new_gid()


@pytest.mark.django_db
def test_when_smaller_than_min_range(settings, allocation_attribute_factory):
    """Test when existing GID is smaller than the minimum of the range."""
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = [range(1000, 2000)]

    # Create an existing GID outside the range
    allocation_attribute_factory(allocation_attribute_type=None, value=999)

    # Call the get_new_gid function
    gid = get_new_gid()

    # Assert that the returned GID is the start of the range
    assert gid == 1000


@pytest.mark.django_db
def test_multiple_gid_ranges(settings, allocation_attribute_factory):
    """Test when multiple GID ranges are configured."""
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = [range(1000, 1100), range(2000, 2100)]

    # Create an existing GID at the end of the first range
    allocation_attribute_factory(allocation_attribute_type=None, value=1099)

    # Call the get_new_gid function
    gid = get_new_gid()

    # Assert that the returned GID is the start of the next range
    assert gid == 2000
