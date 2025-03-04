"""Interface for interacting with the GPFS API."""

from django.conf import settings
from uplink import Consumer, get
from uplink.auth import BasicAuth


class GPFSClient(Consumer):
    """Client for interacting with the GPFS API."""

    def __init__(self):
        """Initialise the client with the base URL and authentication."""
        auth = BasicAuth(settings.GPFS_API_USERNAME, settings.GPFS_API_PASSWORD)
        super().__init__(base_url=settings.GPFS_API_URL, auth=auth)

    @get("users/{username}")
    def user_info(self, username: str):
        """Get information about a user."""
        pass
