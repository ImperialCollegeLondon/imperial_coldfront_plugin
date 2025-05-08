"""Interface for interacting with the GPFS API."""

from collections.abc import Generator
from pathlib import Path

import requests
from django.conf import settings
from uplink import Body, Consumer, get, json, post, response_handler, retry
from uplink.auth import BasicAuth
from uplink.retry.backoff import exponential
from uplink.retry.stop import after_delay
from uplink.retry.when import RetryPredicate, status_5xx

from .tasks import run_in_background


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
        parent_fileset: str,
    ) -> requests.Response:
        """Method (public) to create a fileset in the requested filesystem.

        Args:
            filesystem_name: Name of the filesystem where the fileset will be created.
            fileset_name: Name of the fileset to create (rdf project id).
            owner_id: ID of the owner (pi username).
            group_id: ID of the group (rdf project id).
            path: Path.
            permissions: Permissions.
            parent_fileset: Name of the fileset the new fileset will belong to.

        Returns:
            The response after successfully creating the fileset.
        """
        return self._create_fileset(
            filesystemName=filesystem_name,
            filesetName=fileset_name,
            owner=f"{owner_id}:{group_id}",
            path=path,
            permissions=permissions,
            inodeSpace=parent_fileset,
            permissionChangeMode="chmodAndSetAcl",
            iamMode="advisory",
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

    @check_job_status
    @json
    @post("filesystems/{filesystemName}/filesets/{filesetName}/directory/{path}")
    def _create_fileset_directory(
        self,
        filesystemName: str,
        filesetName: str,
        path: str,
        **data: Body,
    ) -> requests.Response:
        pass

    def create_fileset_directory(
        self,
        filesystem_name: str,
        fileset_name: str,
        path: str,
        allow_existing: bool = False,
    ):
        """Create a new directory within a fileset.

        Args:
          filesystem_name: name of the filesystem containing the fileset.
          fileset_name: name of the fileset in which to create the directory.
          path: location of the directory as a relative path w.r.t the fileset path,
            will create new directories recursively as required.
          allow_existing: if True do not raise an error if the directory already exists.
        """
        try:
            return self._create_fileset_directory(
                filesystem_name,
                fileset_name,
                path,
                user="root",
                group="root",
                permissions="750",
                recursive=True,
            )
        except ErrorWhenProcessingJob as e:
            task_data = e.args[0]
            if allow_existing and task_data["exitCode"] == 6:
                return task_data
            raise

    @json
    @get("filesystems/{filesystemName}/filesets/{filesetName}/quotas")
    def _retrieve_quota_usage(
        self,
        filesystemName: str,
        filesetName: str,
    ) -> requests.Response:
        """Method (private) to retrieve the quota usage of a fileset."""
        pass

    def retrieve_quota_usage(
        self,
        filesystem_name: str,
        fileset_name: str,
    ) -> requests.Response:
        """Method (public) to retrieve the quota usage of a fileset.

        Args:
            filesystem_name: Name of the filesystem to retrieve the quota usage from.
            fileset_name: Name of the fileset to retrieve the quota usage from.

        Returns:
            The block and files usage values.
        """
        response = self._retrieve_quota_usage(
            filesystemName=filesystem_name, filesetName=fileset_name
        )
        data = response.json()

        block_usage = data["quotas"][0][
            "blockUsage"
        ]  # denotes the "Usage": Current capacity quota usage.

        files_usage = data["quotas"][0][
            "filesUsage"
        ]  # denotes the "Number of files in usage": Number of inodes.

        retrieved_data = {
            "block_usage_gb": block_usage / 1024**2,
            "files_usage": files_usage,
        }

        return retrieved_data

    @json
    @get("filesystems/{filesystemName}/quotas")
    def _retrieve_all_fileset_quotas(
        self,
        filesystemName: str,
    ) -> requests.Response:
        """Method (private) to retrieve the quotas of a filesystem."""

    def retrieve_all_fileset_usages(self, filesystem_name: str):
        """Get the quotas for all filesets.

        Arguments:
            filesystem_name: Name of the filesystem to retrieve the quota usage from.
        """
        data = self._retrieve_all_fileset_quotas(filesystem_name).json()
        return {
            quota["objectName"]: {
                "files": quota["filesUsage"],
                "block_gb": quota["blockUsage"] / 1024**2,
            }
            for quota in data["quotas"]
            if quota["quotaType"] == "FILESET"
        }


class FilesetCreationError(Exception):
    """Raised when a problem is encountered when creating a fileset."""


class FilesetQuotaError(Exception):
    """Raised when a problem is encountered when setting a fileset quota."""


def _create_fileset_set_quota(
    filesystem_name: str,
    fileset_name: str,
    owner_id: str,
    group_id: str,
    parent_fileset_path: Path,
    relative_projects_path: Path,
    permissions: str,
    block_quota: str,
    files_quota: str,
    parent_fileset: str,
):
    """Create a fileset and set a quota in the requested filesystem."""
    client = GPFSClient()
    client.create_fileset_directory(
        filesystem_name,
        parent_fileset,
        relative_projects_path,
        allow_existing=True,
    )

    try:
        client.create_fileset(
            filesystem_name,
            fileset_name,
            owner_id,
            group_id,
            str(parent_fileset_path / relative_projects_path / fileset_name),
            permissions,
            parent_fileset,
        ).raise_for_status()
    except requests.HTTPError as e:
        raise FilesetCreationError(
            f"Error when creating fileset '{fileset_name}' - {e.response.content}"
        ) from e

    try:
        client.set_quota(
            filesystem_name, fileset_name, block_quota, files_quota
        ).raise_for_status()
    except requests.HTTPError as e:
        raise FilesetQuotaError(
            f"Error when setting fileset '{fileset_name}' quota  - {e.response.content}"
        ) from e


create_fileset_set_quota_in_background = run_in_background(_create_fileset_set_quota)
