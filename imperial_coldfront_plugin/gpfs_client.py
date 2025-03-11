"""Interface for interacting with the GPFS API."""

from collections.abc import Generator

import requests
from django.conf import settings
from uplink import Body, Consumer, delete, get, post, retry, returns
from uplink.auth import BasicAuth
from uplink.retry.backoff import exponential
from uplink.retry.stop import after_delay
from uplink.retry.when import RetryPredicate, status_5xx


class ErrorWhenProcessingJob(Exception):
    """Handles errors in asynchronous jobs."""

    def __init__(self, value: dict):
        """Initialises the exception with the error information."""
        self.value = value

    def __str__(self) -> str:
        """Builds the error string."""
        return repr(self.value)


class JobTimeout(Exception):
    """Raises an exception when a job times out."""


class JobRunning(RetryPredicate):
    """Checks the job status to decide it there should be a retry."""

    def should_retry_after_response(self, response: requests.Response) -> bool:
        """Check the response to decide if it should retry.

        Args:
            response: The response to explore.

        Raises:
            ErrorWhenProcessingJob, if the job status is FAILED.
            JobTimeout, if the job status is TIMEOUT.

        Returns:
            True if the request should be retried, False otherwise.
        """
        if not 200 <= response.status_code < 300:
            return False

        job_data: dict = response.json()["jobs"][0]
        if job_data["status"] == "FAILED":
            job_data["result"]["jobId"] = job_data["jobId"]
            raise ErrorWhenProcessingJob(job_data["result"])
        elif job_data["status"] == "RUNNING":
            return True

        return False


class TimeoutWithException(after_delay):
    """Stops the retry with a custom exception when there is too much delay."""

    def __call__(self) -> Generator[bool, float, None]:
        """Checks if delay is beyond maximum timeout.

        Raises:
            TimeoutError, if delay is greater than the maximum delay.

        Yields:
            False, if delay has not reached the maximum.
        """
        while True:
            delay = yield 0
            if self._max_delay < delay:
                raise TimeoutError()
            yield False


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

    @retry(
        when=JobRunning() | status_5xx(),
        backoff=exponential(),
        stop=TimeoutWithException(settings.GPFS_API_TIMEOUT),
    )
    @get("jobs/{jobId}")
    def _get_job_status(self, jobId: int):
        """Query the status of a job."""

    @delete("jobs/{jobId}")
    def _cancel_job(self, jobId: int):
        """Cancel an asynchronous job."""

    def get_job_status(self, jobId: int) -> requests.Response:
        """Query the status of a job and handles the response.

        Captures the TimeoutError, adds the 'jobId', sends order to cancel the job
         and raises them again.

        Args:
            jobId: The ID of the job to get the status for.

        Raises:
            TimeoutError including the jobId.

        Return:
            The full command response, if completed successfully.
        """
        try:
            return self._get_job_status(jobId)
        except TimeoutError:
            self._cancel_job(jobId)
            raise TimeoutError(
                f"JobID={jobId} failed to complete in time. Cancelling..."
            )
