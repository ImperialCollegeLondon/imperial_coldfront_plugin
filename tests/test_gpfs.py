import urllib
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from imperial_coldfront_plugin.gpfs_client import (
    DirectoryExistsError,
    FilesetPathInfo,
    GPFSClient,
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
PERMISSIONS = "755"
PARENT_FILESET = "parentfileset"
HEADERS = {"Authorization": "Basic Og=="}


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
def request_mock(mocker):
    """Mock requests.Session.request to return a MockResponse."""
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


@pytest.fixture
def completed_job_status(mocker):
    """Mock for a completed job status response."""
    return mocker.Mock(return_value=make_response({"jobs": [{"status": "COMPLETED"}]}))


def test_paginate():
    """Test the _paginate method handles multiple pages."""
    first_page = {"paging": {"lastId": 100}, "quotas": [{"id": 1}]}
    second_page = {"quotas": [{"id": 2}]}

    api_mock = Mock(
        side_effect=[
            make_response(first_page),
            make_response(second_page),
        ]
    )

    items = GPFSClient()._paginate(
        api_mock, item_key="quotas", filesystemName=FILESYSTEM_NAME
    )

    assert items == [{"id": 1}, {"id": 2}]
    assert api_mock.call_count == 2
    _, second_kwargs = api_mock.call_args_list[1]
    assert "lastId" in second_kwargs and second_kwargs["lastId"] == 100


def test__filesystems(settings, request_mock):
    """Test that _filesystems method works correctly."""
    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._filesystems(lastId=10)

    request_mock.assert_called_once_with(
        method="GET",
        url="http://example.com/api/filesystems",
        params={"lastId": "10"},
        headers=HEADERS,
    )


def test_filesystems(mocker):
    """Test that filesystems wrapper works correctly."""
    client = GPFSClient()
    _filesystems_mock = mocker.patch.object(
        client,
        "_filesystems",
        autospec=True,
        side_effect=[make_response({"filesystems": [{"name": FILESYSTEM_NAME}]})],
    )

    response = client.filesystems()
    _filesystems_mock.assert_called_once_with()
    assert response == [{"name": FILESYSTEM_NAME}]


def test__retrieve_quota_usage(settings, request_mock):
    """Test that _retrieve_quota_usage method works correctly."""
    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._retrieve_quota_usage(
        filesystemName=FILESYSTEM_NAME, filesetName=FILESET_NAME, lastId=30
    )

    request_mock.assert_called_once_with(
        method="GET",
        url=f"http://example.com/api/filesystems/{FILESYSTEM_NAME}/filesets/{FILESET_NAME}/quotas",
        params={"lastId": "30"},
        headers=HEADERS,
        json={},
    )


def test__retrieve_all_fileset_quotas(settings, request_mock):
    """Test that _retrieve_all_fileset_quotas method works correctly."""
    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._retrieve_all_fileset_quotas(filesystemName=FILESYSTEM_NAME, lastId=20)

    request_mock.assert_called_once_with(
        method="GET",
        url=(
            f"http://example.com/api/filesystems/{FILESYSTEM_NAME}/quotas"
            f"?filter=quotaType=FILESET"
        ),
        params={"lastId": "20"},
        headers=HEADERS,
        json={},
    )


def test_get_directory_acl(settings, fileset_path_info, request_mock):
    """Test that get_directory_acl method works correctly."""
    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client.get_directory_acl(
        filesystem_name=FILESYSTEM_NAME,
        path=fileset_path_info.fileset_absolute_path,
    )

    assert request_mock.called
    _, kwargs = request_mock.call_args
    url = kwargs.get("url", "")

    request_mock.assert_called_once_with(
        method="GET",
        url=url,
        headers=HEADERS,
        json={},
    )


def test__get_job_status(settings, request_mock):
    """Test that _get_job_status method works correctly."""
    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._get_job_status(jobId="12345")

    request_mock.assert_called_once_with(
        method="GET",
        url="http://example.com/api/jobs/12345",
        headers=HEADERS,
    )


def test__create_fileset(settings, completed_job_status, request_mock):
    """Test that _create_fileset method works correctly."""
    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._get_job_status = completed_job_status

    expected_path = str(
        Path(
            FILESYSTEM_MOUNT_PATH,
            TOP_LEVEL_DIRECTORIES,
            FACULTY,
            DEPARTMENT,
            GROUP_NAME,
            FILESET_NAME,
        )
    )

    client._create_fileset(
        filesystemName=FILESYSTEM_NAME,
        filesetName=FILESET_NAME,
        ownerId=OWNER_ID,
        groupId=GROUP_ID,
        path=expected_path,
        permissions=PERMISSIONS,
        parent_fileset=PARENT_FILESET,
    )

    request_mock.assert_called_once_with(
        method="POST",
        url=f"http://example.com/api/filesystems/{FILESYSTEM_NAME}/filesets",
        headers=HEADERS,
        json={
            "filesetName": FILESET_NAME,
            "ownerId": OWNER_ID,
            "groupId": GROUP_ID,
            "path": expected_path,
            "permissions": PERMISSIONS,
            "parent_fileset": PARENT_FILESET,
        },
    )


def test_create_fileset(mocker):
    """Test that create_fileset wrapper works correctly."""
    client = GPFSClient()
    _create_fileset_mock = mocker.patch.object(
        client, "_create_fileset", autospec=True, return_value=None
    )

    response = client.create_fileset(
        filesystem_name=FILESYSTEM_NAME,
        fileset_name=FILESET_NAME,
        owner_id=OWNER_ID,
        group_id=GROUP_ID,
        path=(
            f"{FILESYSTEM_MOUNT_PATH}/{TOP_LEVEL_DIRECTORIES}/{FACULTY}/"
            f"{DEPARTMENT}/{GROUP_NAME}/{FILESET_NAME}"
        ),
        permissions=PERMISSIONS,
        parent_fileset=PARENT_FILESET,
    )

    _create_fileset_mock.assert_called_once_with(
        filesystemName=FILESYSTEM_NAME,
        filesetName=FILESET_NAME,
        owner=f"{OWNER_ID}:{GROUP_ID}",
        path=f"{FILESYSTEM_MOUNT_PATH}/{TOP_LEVEL_DIRECTORIES}/{FACULTY}/{DEPARTMENT}/{GROUP_NAME}/{FILESET_NAME}",
        permissions=PERMISSIONS,
        inodeSpace=PARENT_FILESET,
        permissionChangeMode="chmodAndSetAcl",
        iamMode="advisory",
    )

    assert response is None


def test__set_quota(settings, completed_job_status, request_mock):
    """Test that _set_quota method works correctly."""
    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._get_job_status = completed_job_status

    client._set_quota(
        filesystemName=FILESYSTEM_NAME,
        filesetName=FILESET_NAME,
        blockQuota=BLOCK_QUOTA,
        filesQuota=FILES_QUOTA,
    )

    request_mock.assert_called_once_with(
        method="POST",
        url=f"http://example.com/api/filesystems/{FILESYSTEM_NAME}/quotas",
        headers=HEADERS,
        json={
            "filesetName": FILESET_NAME,
            "blockQuota": BLOCK_QUOTA,
            "filesQuota": FILES_QUOTA,
        },
    )


def test_set_quota(mocker):
    """Test that set_quota wrapper works correctly."""
    client = GPFSClient()
    _set_quota_mock = mocker.patch.object(
        client, "_set_quota", autospec=True, return_value=None
    )

    response = client.set_quota(
        filesystem_name=FILESYSTEM_NAME,
        fileset_name=FILESET_NAME,
        block_quota=BLOCK_QUOTA,
        files_quota=FILES_QUOTA,
    )

    _set_quota_mock.assert_called_once_with(
        filesystemName=FILESYSTEM_NAME,
        objectName=FILESET_NAME,
        operationType="setQuota",
        quotaType="FILESET",
        blockSoftLimit=BLOCK_QUOTA,
        blockHardLimit=BLOCK_QUOTA,
        filesSoftLimit=FILES_QUOTA,
        filesHardLimit=FILES_QUOTA,
        filesGracePeriod="null",
        blockGracePeriod="null",
    )

    assert response is None


def test__create_fileset_directory(settings, completed_job_status, request_mock):
    """Test that _create_fileset_directory method works correctly."""
    settings.GPFS_API_URL = "http://example.com/api/v1"

    client = GPFSClient()
    client._get_job_status = completed_job_status

    path = str(
        Path(
            FILESYSTEM_MOUNT_PATH,
            TOP_LEVEL_DIRECTORIES,
            FACULTY,
            DEPARTMENT,
            GROUP_NAME,
            FILESET_NAME,
        )
    )

    client._create_fileset_directory(
        filesystemName=FILESYSTEM_NAME,
        filesetName=FILESET_NAME,
        path=path,
        permissions=PERMISSIONS,
        allow_existing=False,
    )

    expected_url = (
        f"http://example.com/api/filesystems/{FILESYSTEM_NAME}/filesets/{FILESET_NAME}/directory/"
        + urllib.parse.quote(path, safe="")
    )

    request_mock.assert_called_once_with(
        method="POST",
        url=expected_url,
        headers=HEADERS,
        json={
            "permissions": PERMISSIONS,
            "allow_existing": False,
        },
    )


def test_create_fileset_directory(mocker):
    """Test that create_fileset_directory wrapper works correctly."""
    client = GPFSClient()
    _create_fileset_directory_mock = mocker.patch.object(
        client, "_create_fileset_directory", autospec=True, return_value=None
    )

    path = str(
        Path(
            FILESYSTEM_MOUNT_PATH,
            TOP_LEVEL_DIRECTORIES,
            FACULTY,
            DEPARTMENT,
            GROUP_NAME,
            FILESET_NAME,
        )
    )

    response = client.create_fileset_directory(
        filesystem_name=FILESYSTEM_NAME,
        fileset_name=FILESET_NAME,
        path=path,
        permissions=PERMISSIONS,
        allow_existing=False,
    )

    _create_fileset_directory_mock.assert_called_once_with(
        FILESYSTEM_NAME,
        FILESET_NAME,
        path,
        user="root",
        group="root",
        permissions=PERMISSIONS,
        recursive=True,
    )

    assert response is None
