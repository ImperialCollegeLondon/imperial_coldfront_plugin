"""Interface for interacting with the GPFS API."""

import requests
from django.conf import settings
from uplink import Consumer, get, returns
from uplink.auth import BasicAuth


class GPFSClient(Consumer):
    """Client for interacting with the GPFS API."""

    def __init__(self) -> None:
        """Initialise the client with the base URL and authentication."""
        session = requests.Session()
        session.verify = settings.GPFS_API_VERIFY
        auth = BasicAuth(settings.GPFS_API_USERNAME, settings.GPFS_API_PASSWORD)
        super().__init__(base_url=settings.GPFS_API_URL, auth=auth, client=session)

    @returns.json
    @get("filesystems")
    def filesystems(self) -> str:
        """Return the information on the filesystems available."""
