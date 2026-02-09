import urllib
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from imperial_coldfront_plugin.gpfs_client import (
    DirectoryExistsError,
    FilesetPathInfo,
    create_fileset_set_quota,
)

FILESYSTEM_MOUNT_PATH = Path("/")
FILESYSTEM_NAME = "gpfs0"
TOP_LEVEL_DIRECTORIES = Path("top/level")
FACULTY = "sci"
DEPARTMENT = "compsci"
GROUP_NAME = "mygroup"
FILESET_NAME = "myfileset"
OWNER_ID = "someowner"
GROUP_ID = "rdf-somegroup"
BLOCK_QUOTA = "123456T"
FILES_QUOTA = "654321T"


@pytest.fixture(autouse=True)
def patch_request_session(mocker):
    """Backstop to prevent real HTTP requests during tests.

    Raises an error if an un-mocked HTTP request is attempted.
    """
    return mocker.patch(
        "requests.Session.send",
        side_effect=RuntimeError(
            "Un-mocked HTTP request, tests should never make it here."
        ),
    )


@pytest.fixture
def fileset_path_info():
    """A FilesetPathInfo for testing."""
    return FilesetPathInfo(
        filesystem_mount_path=FILESYSTEM_MOUNT_PATH,
        filesystem_name=FILESYSTEM_NAME,
        top_level_directories=TOP_LEVEL_DIRECTORIES,
        faculty=FACULTY,
        department=DEPARTMENT,
        group_id=GROUP_NAME,
        fileset_name=FILESET_NAME,
    )


def test_fileset_path_info(fileset_path_info):
    """Test the FilesetPathInfo dataclass."""
    assert fileset_path_info.parent_fileset_absolute_path == Path(
        FILESYSTEM_MOUNT_PATH,
        FILESYSTEM_NAME,
        TOP_LEVEL_DIRECTORIES,
        FACULTY,
    )
    assert fileset_path_info.parent_fileset_path_relative_to_filesystem == (
        TOP_LEVEL_DIRECTORIES / FACULTY
    )
    assert fileset_path_info.group_directory_path_relative_to_parent_fileset == Path(
        DEPARTMENT, GROUP_NAME
    )
    assert list(fileset_path_info.iter_intermediate_relative_directory_paths()) == [
        Path(DEPARTMENT),
        Path(DEPARTMENT, GROUP_NAME),
    ]
    assert fileset_path_info.fileset_path_relative_to_parent_fileset == Path(
        DEPARTMENT, GROUP_NAME, FILESET_NAME
    )
    assert fileset_path_info.fileset_absolute_path == Path(
        FILESYSTEM_MOUNT_PATH,
        FILESYSTEM_NAME,
        TOP_LEVEL_DIRECTORIES,
        FACULTY,
        DEPARTMENT,
        GROUP_NAME,
        FILESET_NAME,
    )
    assert fileset_path_info.fileset_path_relative_to_filesystem == (
        TOP_LEVEL_DIRECTORIES / FACULTY / DEPARTMENT / GROUP_NAME / FILESET_NAME
    )


@pytest.fixture
def client_mock(mocker):
    """Mock the GPFS client."""
    mock = mocker.patch("imperial_coldfront_plugin.gpfs_client.GPFSClient")
    return mock()


@pytest.fixture
def mock_requests(mocker):
    """Mock the requests module."""
    mock = mocker.patch("requests.Session.request")
    mock.return_value.status_code = 200
    return mock


def test_create_fileset_set_quota(client_mock, fileset_path_info, settings):
    """Test creating a fileset, setting ACLs and quotas."""
    create_fileset_set_quota(
        fileset_path_info,
        OWNER_ID,
        GROUP_ID,
        settings.GPFS_FILESET_POSIX_PERMISSIONS,
        settings.GPFS_FILESET_ACL,
        settings.GPFS_PARENT_DIRECTORY_POSIX_PERMISSIONS,
        settings.GPFS_PARENT_DIRECTORY_ACL,
        BLOCK_QUOTA,
        FILES_QUOTA,
    )
    intermediate_relative_paths = [Path(DEPARTMENT), Path(DEPARTMENT, GROUP_NAME)]
    assert client_mock.create_fileset_directory.call_args_list == [
        call(
            FILESYSTEM_NAME,
            FACULTY,
            path,
            allow_existing=False,
            permissions=settings.GPFS_PARENT_DIRECTORY_POSIX_PERMISSIONS,
        )
        for path in intermediate_relative_paths
    ]
    assert client_mock.set_directory_acl.call_count == 3
    assert client_mock.set_directory_acl.call_args_list[:2] == [
        call(
            FILESYSTEM_NAME,
            TOP_LEVEL_DIRECTORIES / FACULTY / path,
            acl=settings.GPFS_PARENT_DIRECTORY_ACL,
        )
        for path in intermediate_relative_paths
    ]

    client_mock.create_fileset.assert_called_once_with(
        FILESYSTEM_NAME,
        FILESET_NAME,
        OWNER_ID,
        f"IC\\{GROUP_ID}",
        fileset_path_info.fileset_absolute_path,
        settings.GPFS_FILESET_POSIX_PERMISSIONS,
        FACULTY,
    )

    client_mock.set_quota.assert_called_once_with(
        FILESYSTEM_NAME,
        FILESET_NAME,
        BLOCK_QUOTA,
        FILES_QUOTA,
    )

    client_mock.set_directory_acl.assert_called_with(
        FILESYSTEM_NAME,
        TOP_LEVEL_DIRECTORIES / FACULTY / DEPARTMENT / GROUP_NAME / FILESET_NAME,
        acl=settings.GPFS_FILESET_ACL,
    )


def test_create_fileset_set_quota_existing_directory(
    client_mock, fileset_path_info, settings
):
    """If an intermediate directory already exists we continue and don't set the ACL."""
    client_mock.create_fileset_directory.side_effect = [DirectoryExistsError, None]

    create_fileset_set_quota(
        fileset_path_info,
        OWNER_ID,
        GROUP_ID,
        settings.GPFS_FILESET_POSIX_PERMISSIONS,
        settings.GPFS_FILESET_ACL,
        settings.GPFS_PARENT_DIRECTORY_POSIX_PERMISSIONS,
        settings.GPFS_PARENT_DIRECTORY_ACL,
        BLOCK_QUOTA,
        FILES_QUOTA,
    )
    intermediate_relative_paths = [Path(DEPARTMENT), Path(DEPARTMENT, GROUP_NAME)]
    # create fileset directory called twice
    assert client_mock.create_fileset_directory.call_args_list == [
        call(
            FILESYSTEM_NAME,
            FACULTY,
            path,
            allow_existing=False,
            permissions=settings.GPFS_PARENT_DIRECTORY_POSIX_PERMISSIONS,
        )
        for path in intermediate_relative_paths
    ]

    # set acl called only twice skipping first call of create_fileset_directory
    assert client_mock.set_directory_acl.call_count == 2
    assert client_mock.set_directory_acl.call_args_list[0] == call(
        FILESYSTEM_NAME,
        TOP_LEVEL_DIRECTORIES / FACULTY / DEPARTMENT / GROUP_NAME,
        acl=settings.GPFS_PARENT_DIRECTORY_ACL,
    )
    assert (
        call(
            FILESYSTEM_NAME,
            acl=settings.GPFS_PARENT_DIRECTORY_ACL,
        )
        not in client_mock.set_directory_acl.call_args_list
    )


def make_response(data: dict[str, object]) -> Mock:
    """Helper to make a mock response with .json() method."""
    response_mock = Mock()
    response_mock.json = Mock(return_value=data)
    response_mock.raise_for_status = Mock()
    return response_mock


def test_paginate():
    """Test the _paginate method handles multiple pages."""
    from imperial_coldfront_plugin.gpfs_client import GPFSClient

    first_page = {"paging": {"lastId": 100}, "quotas": [{"id": 1}]}
    second_page = {"quotas": [{"id": 2}]}

    api_mock = Mock(
        side_effect=[
            make_response(first_page),
            make_response(second_page),
        ]
    )

    items = GPFSClient()._paginate(api_mock, item_key="quotas", filesystemName="gpfs")

    assert items == [{"id": 1}, {"id": 2}]
    assert api_mock.call_count == 2
    _, second_kwargs = api_mock.call_args_list[1]
    assert "lastId" in second_kwargs and second_kwargs["lastId"] == 100


def test__filesystems(settings, mock_requests):
    """Test that _filesystems method works correctly."""
    from imperial_coldfront_plugin.gpfs_client import GPFSClient

    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._filesystems(lastId=10)

    mock_requests.assert_called_once_with(
        method="GET",
        url="http://example.com/api/filesystems",
        params={"lastId": "10"},
        headers={"Authorization": "Basic Og=="},
    )


def test__retrieve_all_fileset_quotas(settings, mock_requests):
    """Test that _retrieve_all_fileset_quotas method workscorrectly."""
    from imperial_coldfront_plugin.gpfs_client import GPFSClient

    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._retrieve_all_fileset_quotas(filesystemName="gpfs0", lastId=20)

    mock_requests.assert_called_once_with(
        method="GET",
        url="http://example.com/api/filesystems/gpfs0/quotas?filter=quotaType=FILESET",
        params={"lastId": "20"},
        headers={"Authorization": "Basic Og=="},
        json={},
    )


def test__retrieve_quota_usage(settings, mock_requests):
    """Test that _retrieve_quota_usage method works correctly."""
    from imperial_coldfront_plugin.gpfs_client import GPFSClient

    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._retrieve_quota_usage(
        filesystemName="gpfs0", filesetName="myfileset", lastId=30
    )

    mock_requests.assert_called_once_with(
        method="GET",
        url="http://example.com/api/filesystems/gpfs0/filesets/myfileset/quotas",
        params={"lastId": "30"},
        headers={"Authorization": "Basic Og=="},
        json={},
    )


def test_get_directory_acl(settings, mock_requests):
    """Test that get_directory_acl method works correctly."""
    from imperial_coldfront_plugin.gpfs_client import GPFSClient

    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    path = "path/to/some/directory"
    client.get_directory_acl(
        filesystem_name="gpfs0",
        path=path,
    )

    expected_url = (
        "http://example.com/api/filesystems/gpfs0/acl/" + urllib.parse.quote_plus(path)
    )

    mock_requests.assert_called_once_with(
        method="GET",
        url=expected_url,
        headers={"Authorization": "Basic Og=="},
        json={},
    )


def test__get_job_status(settings, mock_requests):
    """Test that _get_job_status method works correctly."""
    from imperial_coldfront_plugin.gpfs_client import GPFSClient

    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._get_job_status(jobId="12345")

    mock_requests.assert_called_once_with(
        method="GET",
        url="http://example.com/api/jobs/12345",
        headers={"Authorization": "Basic Og=="},
    )


def test__create_fileset(settings, mock_requests):
    """Test that _create_fileset method works correctly."""
    from imperial_coldfront_plugin.gpfs_client import GPFSClient

    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._get_job_status = Mock(
        return_value=make_response({"jobs": [{"status": "COMPLETED"}]})
    )

    client._create_fileset(
        filesystemName="gpfs0",
        filesetName="myfileset",
        ownerId="owner",
        groupId="group",
        absolutePath="/gpfs0/path/to/fileset",
        permissions="755",
        faculty="sci",
    )

    mock_requests.assert_called_once_with(
        method="POST",
        url="http://example.com/api/filesystems/gpfs0/filesets",
        headers={"Authorization": "Basic Og=="},
        json={
            "filesetName": "myfileset",
            "ownerId": "owner",
            "groupId": "group",
            "absolutePath": "/gpfs0/path/to/fileset",
            "permissions": "755",
            "faculty": "sci",
        },
    )


def test__set_quota(settings, mock_requests):
    """Test that _set_quota method works correctly."""
    from imperial_coldfront_plugin.gpfs_client import GPFSClient

    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._get_job_status = Mock(
        return_value=make_response({"jobs": [{"status": "COMPLETED"}]})
    )

    client._set_quota(
        filesystemName="gpfs0",
        filesetName="myfileset",
        blockQuota="123456T",
        filesQuota="654321T",
    )

    mock_requests.assert_called_once_with(
        method="POST",
        url="http://example.com/api/filesystems/gpfs0/quotas",
        headers={"Authorization": "Basic Og=="},
        json={
            "filesetName": "myfileset",
            "blockQuota": "123456T",
            "filesQuota": "654321T",
        },
    )


def test__create_fileset_directory(settings, mock_requests):
    """Test that _create_fileset_directory method works correctly."""
    from imperial_coldfront_plugin.gpfs_client import GPFSClient

    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._get_job_status = Mock(
        return_value=make_response({"jobs": [{"status": "COMPLETED"}]})
    )

    path = "path/to/directory"

    client._create_fileset_directory(
        filesystemName="gpfs0",
        filesetName="myfileset",
        path=path,
        permissions="755",
        allow_existing=False,
    )

    expected_url = (
        "http://example.com/api/filesystems/gpfs0/filesets/myfileset/directory/"
        + urllib.parse.quote_plus(path)
    )

    mock_requests.assert_called_once_with(
        method="POST",
        url=expected_url,
        headers={"Authorization": "Basic Og=="},
        json={
            "permissions": "755",
            "allow_existing": False,
        },
    )
