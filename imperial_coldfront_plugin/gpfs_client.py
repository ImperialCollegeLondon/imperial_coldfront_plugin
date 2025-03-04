"""Interface for interacting with the GPFS API."""

import requests
from django.conf import settings
from uplink import Consumer, get
from uplink.auth import BasicAuth


class GPFSClient(Consumer):
    """Client for interacting with the GPFS API."""

    def __init__(self) -> None:
        """Initialise the client with the base URL and authentication."""
        session = requests.Session()
        auth = BasicAuth(settings.GPFS_API_USERNAME, settings.GPFS_API_PASSWORD)
        super().__init__(base_url=settings.GPFS_API_URL, auth=auth, session=session)

    @get("filesystems")
    def filesystems(self) -> str:
        """Return the information on the filesystems available."""
