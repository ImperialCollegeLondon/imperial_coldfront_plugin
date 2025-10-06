"""Interface for interacting with the GPFS API."""

import logging
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import requests
from django.conf import settings
from uplink import Body, Consumer, get, json, post, put, response_handler, retry
from uplink.auth import BasicAuth
from uplink.retry.backoff import exponential
from uplink.retry.stop import after_delay
from uplink.retry.when import RetryPredicate, status_5xx

from .acl import ACL


class ErrorWhenProcessingJob(Exception):
    """Handles errors in asynchronous jobs."""


class JobTimeout(Exception):
    """Raises an exception when a job times out."""


class JobResponseData(TypedDict):
    """TypedDict for the result of a job."""

    status: str
    jobId: str
    result: dict[str, str]


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

        job_data: JobResponseData = response.json()["jobs"][0]
        if job_data["status"] == "FAILED":
            job_data["result"]["jobId"] = job_data["jobId"]
            raise ErrorWhenProcessingJob(job_data["result"])
        elif job_data["status"] == "RUNNING":
            return True

        return False


class TimeoutWithException(after_delay):
    """Stops the retry with a custom exception when there is too much delay."""

    def __call__(self) -> Generator[bool | float, float, None]:
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
    """Client for interacting with the GPFS API.

    This class follows some general design patterns:
    - Methods that make requests to the GPFS API are split into public and private
      methods. The private methods are prefixed with an underscore and are decorated
      with the appropriate uplink decorators to define the HTTP method, endpoint,
      and any response handling. The public methods handle any additional logic,
      error handling, and return the final response to create an easy to use interface.
    - Asynchronous operations (e.g. creating a fileset) are handled by making the
      initial request in a private method, then polling the job status using a retry
      mechanism until the job completes or fails. Polling uses exponential backoff
      and a maximum timeout (defined by settings.GPFS_API_TIMEOUT).
    - Error handling is implemented to raise custom exceptions for each api call and
      to provide opportunities for flow control based on specific error conditions.
    """

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
    def _get_job_status(  # type: ignore[empty-body]
        self, jobId: int
    ) -> requests.Response:
        """Query the status of a job."""

    @get("filesystems")
    def filesystems(self) -> requests.Response:  # type: ignore[empty-body]
        """Return the information on the filesystems available."""

    @check_job_status
    @json
    @post("filesystems/{filesystemName}/filesets")
    def _create_fileset(  # type: ignore[empty-body]
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
        path: str | Path,
        permissions: str,
        parent_fileset: str,
    ) -> requests.Response:
        """Method (public) to create a fileset in the requested filesystem.

        Args:
            filesystem_name: Name of the filesystem where the fileset will be created.
            fileset_name: Name of the fileset to create (rdf project id).
            owner_id: ID of the owner (pi username).
            group_id: ID of the group (rdf project id).
            path: Absolute path where the fileset will be created.
            permissions: Permissions.
            parent_fileset: Name of the fileset the new fileset will beloong to.

        Returns:
            The response after successfully creating the fileset.
        """
        try:
            response = self._create_fileset(
                filesystemName=filesystem_name,
                filesetName=fileset_name,
                owner=f"{owner_id}:{group_id}",
                path=str(path),
                permissions=permissions,
                inodeSpace=parent_fileset,
                permissionChangeMode="chmodAndSetAcl",
                iamMode="advisory",
            )
            response.raise_for_status()
            return response
        except requests.HTTPError as e:
            raise FilesetCreationError(
                f"Error creating fileset '{fileset_name}' - {e.response.json()}"
            ) from e
        except ErrorWhenProcessingJob as e:
            raise FilesetCreationError(
                f"Error creating fileset '{fileset_name}' - {e.args[0]}"
            ) from e

    @check_job_status
    @json
    @post("filesystems/{filesystemName}/quotas")
    def _set_quota(  # type: ignore[empty-body]
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
        try:
            response = self._set_quota(
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
            response.raise_for_status()
            return response
        except requests.HTTPError as e:
            raise FilesetQuotaError(
                f"Error whilst setting fileset quota for '{fileset_name}' - "
                f"{e.response.json()}"
            ) from e
        except ErrorWhenProcessingJob as e:
            raise FilesetQuotaError(
                f"Error whilst setting fileset quota for '{fileset_name}' - {e.args[0]}"
            ) from e

    @check_job_status
    @json
    @post("filesystems/{filesystemName}/filesets/{filesetName}/directory/{path}")
    def _create_fileset_directory(  # type: ignore[empty-body]
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
        path: str | Path,
        permissions: str,
        allow_existing: bool = False,
    ) -> requests.Response:
        """Create a new directory within a fileset.

        Args:
          filesystem_name: name of the filesystem containing the fileset.
          fileset_name: name of the fileset in which to create the directory.
          path: location of the directory as a relative path w.r.t the fileset path,
            will create new directories recursively as required.
          permissions: POSIX permissions to set on the new directory.
          allow_existing: if True do not raise an error if the directory already exists.
        """
        try:
            return self._create_fileset_directory(
                filesystem_name,
                fileset_name,
                str(path),
                user="root",
                group="root",
                permissions=permissions,
                recursive=True,
            )
        except ErrorWhenProcessingJob as e:
            task_data = e.args[0]
            if task_data["exitCode"] == 6:
                if allow_existing:
                    return task_data
                raise DirectoryExistsError(
                    f"Directory {path} already exists in fileset {fileset_name}."
                )
            raise DirectoryCreationError(
                f"Error creating directory {path} in fileset {fileset_name} - "
                f"{task_data}"
            )
        except requests.HTTPError as e:
            raise DirectiorCreationError(
                f"Error creating directory {path} in fileset {fileset_name} - "
                f"{e.response.json()}"
            ) from e

    @json
    @get("filesystems/{filesystemName}/filesets/{filesetName}/quotas")
    def _retrieve_quota_usage(  # type: ignore[empty-body]
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
    ) -> dict[str, float]:
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
            "block_usage_tb": block_usage / 1024**3,
            "files_usage": files_usage,
        }

        return retrieved_data

    @json
    @get("filesystems/{filesystemName}/quotas")
    def _retrieve_all_fileset_quotas(  # type: ignore[empty-body]
        self,
        filesystemName: str,
    ) -> requests.Response:
        """Method (private) to retrieve the quotas of a filesystem."""

    def retrieve_all_fileset_usages(
        self, filesystem_name: str
    ) -> dict[str, dict[str, float]]:
        """Get the quotas for all filesets.

        Arguments:
            filesystem_name: Name of the filesystem to retrieve the quota usage from.
        """
        data = self._retrieve_all_fileset_quotas(filesystem_name).json()
        return {
            quota["objectName"]: {
                "files_usage": quota["filesUsage"],
                "block_usage_tb": quota["blockUsage"] / 1024**3,
            }
            for quota in data["quotas"]
            if quota["quotaType"] == "FILESET"
        }

    @json
    @get("filesystems/{filesystem_name}/acl/{path}")
    def get_directory_acl(  # type: ignore[empty-body]
        self, filesystem_name: str, path: str
    ) -> requests.Response:
        """Get the ACL of a directory within a filesystem."""

    @check_job_status
    @json
    @put("filesystems/{filesystem_name}/acl/{path}")
    def _set_directory_acl(  # type: ignore[empty-body]
        self, filesystem_name: str, path: str, **data: Body
    ) -> requests.Response:
        pass

    def set_directory_acl(
        self,
        filesystem_name: str,
        path: str | Path,
        acl: ACL,
    ) -> requests.Response:
        """Set the ACL of a directory within a filesystem.

        These ACL's can be applied to both filesets and any directory within the
        filesystem. See the GPFS docs for detail on valid permissions strings. This
        interface only supports setting a single 'allow' entry for owner, group and
        other. Deny entries or multiple entries for any of owner, group or other are
        not supported. Setting flags for any entry is not supported.

        Args:
            filesystem_name: Name of the filesystem containing the directory.
            path: Relative path of the directory within the filesystem.
            acl: The ACL entries to set.
        """
        try:
            response = self._set_directory_acl(
                filesystem_name, str(path), entries=list(acl.iter_as_dicts())
            )
            response.raise_for_status()
            return response
        except requests.HTTPError as e:
            raise UnableToSetACLError(
                f"Error setting ACL on {path} in filesystem {filesystem_name} - "
                f"{e.response.json()}"
            ) from e
        except ErrorWhenProcessingJob as e:
            raise UnableToSetACLError(
                f"Error setting ACL on {path} in filesystem {filesystem_name} - "
                f"{e.args[0]}"
            ) from e


class FilesetCreationError(Exception):
    """Raised when a problem is encountered when creating a fileset."""


class DirectiorCreationError(Exception):
    """Raised when a problem is encountered when creating a directory."""


class FilesetQuotaError(Exception):
    """Raised when a problem is encountered when setting a fileset quota."""


class DirectoryExistsError(Exception):
    """Raised when a directory already exists and allow_existing is False."""


class DirectoryCreationError(Exception):
    """Raised when a problem is encountered when creating a directory."""


class UnableToSetACLError(Exception):
    """Raised when a problem is encountered when setting ACLs on a directory."""


@dataclass
class FilesetPathInfo:
    """Holds information about a fileset path and provides methods to manipulate it.

    The GPFS API requires paths to be specified in different ways for different
    operations. This class provides a single place to manage the logic for this.
    The absolute path of the fileset follows the structure:
        <filesystem_mount_path>/<filesystem_name>/<top_level_directories>/
        <faculty>/<department>/<group_id>/<fileset_name>
    """

    filesystem_mount_path: Path
    filesystem_name: str
    top_level_directories: Path
    faculty: str
    department: str
    group_id: str
    fileset_name: str

    @property
    def parent_fileset_absolute_path(self) -> Path:
        """Get the absolute path of the parent fileset."""
        return Path(
            self.filesystem_mount_path,
            self.filesystem_name,
            self.parent_fileset_path_relative_to_filesystem,
        )

    @property
    def parent_fileset_path_relative_to_filesystem(self) -> Path:
        """Get the path of the parent fileset relative to the filesystem root."""
        return Path(self.top_level_directories, self.faculty)

    @property
    def group_directory_path_relative_to_parent_fileset(self) -> Path:
        """Get the path of the group directory relative to the parent fileset."""
        return Path(self.department, self.group_id)

    def iter_intermediate_relative_directory_paths(self) -> Generator[Path, None, None]:
        """Descend directory tree yielding relative paths w.r.t parent fileset.

        As an example, given the following directory structure:
            /.../parent_fileset/top_level/department/group_id/fileset_name
        This method would yield:
            Path("department")
            Path("department/group_id")
        """
        parts = self.group_directory_path_relative_to_parent_fileset.parts
        for i in range(1, len(parts) + 1):
            yield Path(*parts[:i])

    @property
    def fileset_path_relative_to_parent_fileset(self) -> Path:
        """Get the path of the fileset relative to the parent fileset."""
        return self.group_directory_path_relative_to_parent_fileset / self.fileset_name

    @property
    def fileset_absolute_path(self) -> Path:
        """Get the absolute path of the fileset."""
        return (
            self.parent_fileset_absolute_path
            / self.fileset_path_relative_to_parent_fileset
        )

    @property
    def fileset_path_relative_to_filesystem(self) -> Path:
        """Get the path of the fileset relative to the filesystem root."""
        return (
            self.parent_fileset_path_relative_to_filesystem
            / self.fileset_path_relative_to_parent_fileset
        )


def create_fileset_set_quota(
    fileset_path_info: FilesetPathInfo,
    owner_id: str,
    group_id: str,
    fileset_posix_permissions: str,
    fileset_acl: ACL,
    parent_posix_permissions: str,
    parent_acl: ACL,
    block_quota: str,
    files_quota: str,
    logger: logging.Logger | None = None,
) -> None:
    """Create a fileset and set a quota in the requested filesystem.

    This function carries out the following steps:
    - Create any intermediate directories in the path to the fileset
      (e.g. department and group_id directories).
    - Set the ACLs on any intermediate directories created.
    - Create the fileset.
    - Set the ACLs on the fileset.
    - Set the files and block quota on the fileset.

    Args:
        fileset_path_info: path information for the fileset to create.
        owner_id: ID of the owner (pi username).
        group_id: ID of the group (AD group name).
        fileset_posix_permissions: POSIX permissions to set on the fileset.
        fileset_acl: ACL for the fileset.
        parent_posix_permissions: POSIX permissions to set on any intermediate
            directories created.
        parent_acl: ACL for any intermediate directories created.
        block_quota: Value that specifies the block soft limit and hard limit.
            The number can be specified using the suffix K, M, G, or T.
        files_quota: Value that specifies the inode soft limit and hard limit.
        logger: Logger to use, defaults to the 'django' logger.
    """
    logger = logger or logging.getLogger("django")

    client = GPFSClient()

    for dir_path in fileset_path_info.iter_intermediate_relative_directory_paths():
        try:
            logger.info(
                f"Creating directory '{dir_path}' in fileset "
                f"'{fileset_path_info.faculty}'."
            )
            client.create_fileset_directory(
                fileset_path_info.filesystem_name,
                fileset_path_info.faculty,
                dir_path,
                allow_existing=False,
                permissions=parent_posix_permissions,
            )
        except DirectoryExistsError:
            logger.info("Directory already exists, not creating.")
            continue
        else:
            # only set ACL if we created the directory
            logger.info(
                f"Setting ACL on directory '{dir_path}' in fileset "
                f"'{fileset_path_info.faculty}'."
            )
            client.set_directory_acl(
                fileset_path_info.filesystem_name,
                fileset_path_info.parent_fileset_path_relative_to_filesystem / dir_path,
                acl=parent_acl,
            )

    logger.info(
        f"Creating fileset '{fileset_path_info.fileset_name}' at "
        f"'{fileset_path_info.fileset_absolute_path}'."
    )
    client.create_fileset(
        fileset_path_info.filesystem_name,
        fileset_path_info.fileset_name,
        owner_id,
        f"{settings.AD_DOMAIN}\\{group_id}",
        fileset_path_info.fileset_absolute_path,
        fileset_posix_permissions,
        fileset_path_info.faculty,
    )

    logger.info(f"Setting acl for fileset {fileset_path_info.fileset_name}")
    client.set_directory_acl(
        fileset_path_info.filesystem_name,
        fileset_path_info.fileset_path_relative_to_filesystem,
        acl=fileset_acl,
    )

    logger.info("Setting quota for fileset {fileset_path_info.fileset_name}")
    client.set_quota(
        fileset_path_info.filesystem_name,
        fileset_path_info.fileset_name,
        block_quota,
        files_quota,
    )
