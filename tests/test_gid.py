import pytest
from django.conf import settings

from imperial_coldfront_plugin.gid import get_new_gid


@pytest.mark.django_db
def test_get_new_gid_no_existing_gids():
    """Test when no existing GIDs are present.

    This test checks that get_new_gid returns the first GID in the range
    when no existing GIDs are present.
    """
    # Mock the settings.GID_RANGES
    settings.GID_RANGES = [range(1000, 2000)]

    # Call the get_new_gid function
    gid = get_new_gid()

    # Assert that the returned GID is the start of the range
    assert gid == 1000


@pytest.mark.django_db
def test_no_gid_in_configured_ranges():
    """Test when no GID ranges are configured.

    This test checks that get_new_gid raises a ValueError when no GID ranges
    are configured in the settings.
    """
    # Clear the GID_RANGES setting
    settings.GID_RANGES = []

    # Call the get_new_gid function and expect a ValueError
    with pytest.raises(
        ValueError, match="No available GID found in the configured ranges."
    ):
        get_new_gid()
