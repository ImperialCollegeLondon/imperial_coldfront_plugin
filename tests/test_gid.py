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
