import pytest

from imperial_coldfront_plugin.gid import (
    ALLOWED_GID_RANGES,
    NoGIDAvailableError,
    get_new_gid,
    validate_gid_range_overlap,
    validate_gid_ranges,
)


def test_get_new_gid_no_existing_gids(db, settings):
    """Test when no existing GIDs are present.

    This test checks that get_new_gid returns the first GID in the range
    when no existing GIDs are present.
    """
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = dict(test=[range(1000, 2000)])

    # Call the get_new_gid function
    gid = get_new_gid("test")

    # Assert that the returned GID is the start of the range
    assert gid == 1000


@pytest.fixture(autouse=True)
def ldap_gid_in_use_mock(mocker):
    """Mock the ldap_gid_in_use function to always return False."""
    return mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_gid_in_use", return_value=False
    )


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
    settings, allocation_attribute_factory, existing_gid, raised_error, rdf_allocation
):
    """Test the get_new_gid function with various existing GID scenarios.

    This test checks the behavior of get_new_gid when there are existing GIDs
    in the database, including cases where the existing GID is in the middle of
    the range, at the end of the range, or outside the configured ranges.
    """
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = dict(test=[range(1000, 2000)])

    # Create an existing GID at the end of the range
    allocation_attribute_factory(
        name="GID", value=existing_gid, allocation=rdf_allocation
    )
    if raised_error:
        # Assert that NoGIDAvailableError is raised
        with pytest.raises(NoGIDAvailableError):
            get_new_gid("test")
    else:
        # Call the get_new_gid function
        gid = get_new_gid("test")
        # Assert that the returned GID is the next available GID
        assert gid == existing_gid + 1


def test_when_smaller_than_min_range(
    settings, allocation_attribute_factory, rdf_allocation
):
    """Test when existing GID is smaller than the minimum of the range."""
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = dict(test=[range(1000, 2000)])

    # Create an existing GID outside the range
    allocation_attribute_factory(name="GID", value=999, allocation=rdf_allocation)

    # Call the get_new_gid function
    gid = get_new_gid("test")

    # Assert that the returned GID is the start of the range
    assert gid == 1000


def test_multiple_gid_ranges_overflow(
    settings, allocation_attribute_factory, rdf_allocation
):
    """Test that gid selection moves to the next range if at the end of previous one."""
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = dict(test=[range(1000, 1100), range(2000, 2100)])

    # Create an existing GID at the end of the first range
    allocation_attribute_factory(name="GID", value=1099, allocation=rdf_allocation)

    # Call the get_new_gid function
    gid = get_new_gid("test")

    # Assert that the returned GID is the start of the next range
    assert gid == 2000


def test_multiple_gid_ranges(settings, allocation_attribute_factory, rdf_allocation):
    """Test when multiple GID ranges are configured."""
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = dict(test=[range(1000, 1100), range(2000, 2100)])

    # Create an existing GID in the second range
    allocation_attribute_factory(name="GID", value=2005, allocation=rdf_allocation)

    # Call the get_new_gid function
    gid = get_new_gid("test")

    # Assert that the returned GID is next in the second range
    assert gid == 2006


TEST_GID_START = ALLOWED_GID_RANGES[0].start
TEST_GID_STOP = ALLOWED_GID_RANGES[0].stop


def test_gid_range_validation():
    """Test that valid GID ranges pass validation."""
    validate_gid_ranges(
        [
            range(TEST_GID_START, TEST_GID_START + 1000),
            range(TEST_GID_STOP - 1000, TEST_GID_STOP),
        ]
    )


@pytest.mark.parametrize(
    "invalid_ranges,msg_contains",
    [
        (
            [range(TEST_GID_START - 10, TEST_GID_STOP)],
            "start",
        ),  # start below allowed range
        ([range(TEST_GID_START, TEST_GID_STOP + 5)], "end"),  # Above allowed range
        (
            [
                range(TEST_GID_START, TEST_GID_START + 1000),
                range(TEST_GID_START + 500, TEST_GID_START + 1000),
            ],
            "overlap",
        ),  # Overlapping ranges
        (
            [range(TEST_GID_STOP - 1, TEST_GID_START + 1)],
            "less than start",
        ),  # Invalid range (start >= stop)
        (
            [
                range(TEST_GID_START + 1000, TEST_GID_STOP),
                range(TEST_GID_START, TEST_GID_START + 300),
            ],
            "ascending",
        ),  # Not in ascending order
        ([range(TEST_GID_START, TEST_GID_STOP, 2)], "step"),  # Step not equal to 1,
    ],
)
def test_invalid_gid_range_validation(invalid_ranges, msg_contains):
    """Test that invalid GID ranges raise ValueError."""
    with pytest.raises(ValueError, match=msg_contains):
        validate_gid_ranges(invalid_ranges)


def test_validate_gid_range_neighboring():
    """Test that neighboring GID ranges do not raise ValueError."""
    ranges = dict(
        test1=[range(TEST_GID_START, TEST_GID_START + 500)],
        test2=[range(TEST_GID_START + 500, TEST_GID_START + 1500)],
    )
    validate_gid_range_overlap(ranges)


def test_validate_gid_range_overlap_with_overlap():
    """Test that overlapping GID ranges across different types raise ValueError."""
    ranges = dict(
        test1=[range(TEST_GID_START, TEST_GID_START + 500)],
        test2=[range(TEST_GID_START + 499, TEST_GID_START + 900)],
    )
    with pytest.raises(ValueError, match="Overlapping GID ranges detected"):
        validate_gid_range_overlap(ranges)


def test_new_id_multiple_named_ranges(
    settings, allocation_attribute_factory, rdf_allocation
):
    """Test that get_new_gid correctly handles multiple named ranges."""
    # Override the GID_RANGES setting using the fixture
    settings.GID_RANGES = dict(
        test1=[range(1000, 1100)],
        test2=[range(2000, 2100)],
    )

    # Create existing GID in second range
    allocation_attribute_factory(name="GID", value=2005, allocation=rdf_allocation)

    # Call the get_new_gid function for both range names
    gid1 = get_new_gid("test1")
    gid2 = get_new_gid("test2")

    # Assert that the returned GIDs are correct for each range
    assert gid1 == 1000  # Next available in test1 range
    assert gid2 == 2006  # Next available in test2 range
