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
