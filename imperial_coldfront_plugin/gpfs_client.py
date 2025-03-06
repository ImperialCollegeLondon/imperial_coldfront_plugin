"""Interface for interacting with the GPFS API."""

import requests
from django.conf import settings
from uplink import Body, Consumer, get, post, returns
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
    def filesystems(self) -> dict:
        """Return the information on the filesystems available."""

    @returns.json
    @post("filesystems/{filesystemName}/filesets")
    def create_fileset(self, filesystemName: str, body: Body) -> dict:
        """Creates a new fileset in the requested filesystem."""

    @get("jobs/{jobId}")
    def _get_job_status(self, jobId: int):
        """Query the status of a job."""
