from pathlib import Path
from unittest.mock import call

import pytest

from imperial_coldfront_plugin.gpfs_client import (
    DirectoryExistsError,
    FilesetPathInfo,
    _create_fileset_set_quota,
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


def test_create_fileset_set_quota(client_mock, fileset_path_info, settings):
    """Test creating a fileset, setting ACLs and quotas."""
    _create_fileset_set_quota(
        fileset_path_info,
        OWNER_ID,
        GROUP_ID,
        settings.GPFS_FILESET_POSIX_PERMISSIONS,
        settings.GPFS_FILESET_OWNER_ACL,
        settings.GPFS_FILESET_GROUP_ACL,
        settings.GPFS_FILESET_OTHER_ACL,
        settings.GPFS_PARENT_DIRECTORY_POSIX_PERMISSIONS,
        settings.GPFS_PARENT_DIRECTORY_OWNER_ACL,
        settings.GPFS_PARENT_DIRECTORY_GROUP_ACL,
        settings.GPFS_PARENT_DIRECTORY_OTHER_ACL,
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
            owner_allow_permissions=settings.GPFS_PARENT_DIRECTORY_OWNER_ACL,
            group_allow_permissions=settings.GPFS_PARENT_DIRECTORY_GROUP_ACL,
            other_allow_permissions=settings.GPFS_PARENT_DIRECTORY_OTHER_ACL,
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
        owner_allow_permissions=settings.GPFS_FILESET_OWNER_ACL,
        group_allow_permissions=settings.GPFS_FILESET_GROUP_ACL,
        other_allow_permissions=settings.GPFS_FILESET_OTHER_ACL,
    )


def test_create_fileset_set_quota_existing_directory(
    client_mock, fileset_path_info, settings
):
    """If an intermediate directory already exists we continue and don't set the ACL."""
    client_mock.create_fileset_directory.side_effect = [DirectoryExistsError, None]

    _create_fileset_set_quota(
        fileset_path_info,
        OWNER_ID,
        GROUP_ID,
        settings.GPFS_FILESET_POSIX_PERMISSIONS,
        settings.GPFS_FILESET_OWNER_ACL,
        settings.GPFS_FILESET_GROUP_ACL,
        settings.GPFS_FILESET_OTHER_ACL,
        settings.GPFS_PARENT_DIRECTORY_POSIX_PERMISSIONS,
        settings.GPFS_PARENT_DIRECTORY_OWNER_ACL,
        settings.GPFS_PARENT_DIRECTORY_GROUP_ACL,
        settings.GPFS_PARENT_DIRECTORY_OTHER_ACL,
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
        owner_allow_permissions=settings.GPFS_PARENT_DIRECTORY_OWNER_ACL,
        group_allow_permissions=settings.GPFS_PARENT_DIRECTORY_GROUP_ACL,
        other_allow_permissions=settings.GPFS_PARENT_DIRECTORY_OTHER_ACL,
    )
    assert (
        call(
            FILESYSTEM_NAME,
            owner_allow_permissions=settings.GPFS_PARENT_DIRECTORY_OWNER_ACL,
            group_allow_permissions=settings.GPFS_PARENT_DIRECTORY_GROUP_ACL,
            other_allow_permissions=settings.GPFS_PARENT_DIRECTORY_OTHER_ACL,
        )
        not in client_mock.set_directory_acl.call_args_list
    )
