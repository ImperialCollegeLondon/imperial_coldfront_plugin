"""Interface for interacting with the GPFS API."""

from collections.abc import Generator

import requests
from django.conf import settings
from uplink import Body, Consumer, get, json, post, response_handler, retry
from uplink.auth import BasicAuth
from uplink.retry.backoff import exponential
from uplink.retry.stop import after_delay
from uplink.retry.when import RetryPredicate, status_5xx


class ErrorWhenProcessingJob(Exception):
    """Handles errors in asynchronous jobs."""


class JobTimeout(Exception):
    """Raises an exception when a job times out."""


class JobRunning(RetryPredicate):
    """Checks the job status to decide it there should be a retry."""

    def should_retry_after_response(self, response: requests.Response) -> bool:
        """Check the response to decide if it should retry.

        Args:
            response: The response to explore.

        Raises:
            ErrorWhenProcessingJob: if the job status is FAILED.

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
            JobTimeout: if delay is greater than the maximum delay.

        Yields:
            False, if delay has not reached the maximum.
        """
        while True:
            delay = yield 0
            if self._max_delay < delay:
                raise JobTimeout()
            yield False


@response_handler(requires_consumer=True)
def check_job_status(
    client: "GPFSClient", response: requests.Response
) -> requests.Response:
    """Check the status of the job indicated in the response.

    Args:
        client: Consumer producing the response. It is needed in order to run the
            corresponding `get_job_status` method.
        response: Response of the request to perform a task asynchronously in the
            server, eg. creating a fileset.

    Raises:
        JobTimeout: If executing the job takes too long.
        ErrorWhenProcessingJob: If anything goes wrong when processing the job.

    Returns:
        The response after successfully completing the request.
    """
    try:
        if not 200 <= response.status_code < 300:
            return response

        data = response.json()
        jobId = data["jobs"][0]["jobId"]
        return client._get_job_status(jobId)

    except JobTimeout:
        raise JobTimeout(f"JobID={jobId} failed to complete in time.")


class GPFSClient(Consumer):
    """Client for interacting with the GPFS API."""

    def __init__(self) -> None:
        """Initialise the client with the base URL and authentication."""
        session = requests.Session()
        session.verify = settings.GPFS_API_VERIFY
        auth = BasicAuth(settings.GPFS_API_USERNAME, settings.GPFS_API_PASSWORD)
        super().__init__(base_url=settings.GPFS_API_URL, auth=auth, client=session)

    @retry(
        when=JobRunning() | status_5xx(),
        backoff=exponential(),
        stop=TimeoutWithException(settings.GPFS_API_TIMEOUT),
    )
    @get("jobs/{jobId}")
    def _get_job_status(self, jobId: int) -> requests.Response:
        """Query the status of a job."""

    @get("filesystems")
    def filesystems(self) -> requests.Response:
        """Return the information on the filesystems available."""

    @check_job_status
    @json
    @post("filesystems/{filesystemName}/filesets")
    def _create_fileset(
        self,
        filesystemName: str,
        **data: Body,
    ) -> requests.Response:
        """Method (private) to create a fileset in the requested filesystem."""

    def create_fileset(
        self,
        filesystem_name: str,
        fileset_name: str,
        owner_id: str,
        group_id: str,
        path: str,
        permissions: str,
    ) -> requests.Response:
        """Method (public) to create a fileset in the requested filesystem.

        Args:
            filesystem_name: Name of the filesystem where the fileset will be created.
            fileset_name: Name of the fileset to create (rdf project id).
            owner_id: ID of the owner (pi username).
            group_id: ID of the group (rdf project id).
            path: Path.
            permissions: Permissions.

        Returns:
            The response after successfully creating the fileset.
        """
        return self._create_fileset(
            filesystemName=filesystem_name,
            filesetName=fileset_name,
            owner=f"{owner_id}:{group_id}",
            path=path,
            permissions=permissions,
        )

    @check_job_status
    @json
    @post("filesystems/{filesystemName}/quotas")
    def _set_quota(
        self,
        filesystemName: str,
        **data: Body,
    ) -> requests.Response:
        """Method (private) to set a quota in the requested filesystem."""

    def set_quota(
        self,
        filesystem_name: str,
        fileset_name: str,
        block_quota: str,
        files_quota: str,
    ) -> requests.Response:
        """Method (public) to set a quota in the requested filesystem.

        Args:
            filesystem_name: Name of the filesystem where the quota will be set.
            fileset_name: Name of the fileset to set the quota.
            block_quota: Number that specifies the block soft limit and hard
                    limit. The number can be specified using the suffix K, M, G, or T.
            files_quota: Number that specifies the inode soft limit and hard
                    limit. The number can be specified using the suffix K, M, or G.

        Returns:
            The response after successfully setting the quota.
        """
        return self._set_quota(
            filesystemName=filesystem_name,
            objectName=fileset_name,
            operationType="setQuota",
            quotaType="FILESET",
            blockSoftLimit=block_quota,
            blockHardLimit=block_quota,
            filesSoftLimit=files_quota,
            filesHardLimit=files_quota,
            filesGracePeriod="null",
            blockGracePeriod="null",
        )
