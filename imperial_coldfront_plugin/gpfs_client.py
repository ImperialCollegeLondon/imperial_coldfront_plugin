"""Interface for interacting with the GPFS API."""

from functools import wraps

import requests
from django.conf import settings
from uplink import Body, Consumer, get, post, retry, returns
from uplink.auth import BasicAuth
from uplink.retry.stop import after_delay
from uplink.retry.when import raises


class ErrorWhenProcessingJob(Exception):
    """Handles errors in asynchronous jobs."""


class JobStillBeingProcessed(Exception):
    """Indicates that a job is still being processed."""


def process_jobid_status_request(f):
    """Process the jobid status check, raising custom exceptions if needed."""

    @wraps(f)
    def wrapper(*args, **kwds):
        response = f(*args, **kwds)
        if not 200 <= response.status_code < 300:
            raise response.raise_for_status()

        job_data = response.json()["jobs"][0]
        if job_data["status"] == "FAILED":
            raise ErrorWhenProcessingJob()
        elif job_data["status"] == "RUNNING":
            raise JobStillBeingProcessed()

        return response

    return wrapper


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

    @retry(when=raises(JobStillBeingProcessed), stop=after_delay(60))
    @process_jobid_status_request
    @get("jobs/{jobId}")
    def _get_job_status(self, jobId: int):
        """Query the status of a job."""
