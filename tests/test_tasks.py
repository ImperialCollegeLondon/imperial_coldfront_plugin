import logging
from datetime import datetime

import pytest
from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeUsage,
    AllocationUser,
)

from imperial_coldfront_plugin.forms import RDFAllocationForm
from imperial_coldfront_plugin.gid import get_new_gid
from imperial_coldfront_plugin.gpfs_client import FilesetPathInfo
from imperial_coldfront_plugin.tasks import (
    check_ldap_consistency,
    create_rdf_allocation,
)


@pytest.fixture(autouse=True)
def gpfs_create_fileset_mock(mocker):
    """Mock create_fileset_and_set_quota in tasks.py."""
    return mocker.patch("imperial_coldfront_plugin.tasks.create_fileset_set_quota")


@pytest.fixture(autouse=True)
def ldap_create_group_mock(mocker):
    """Mock ldap_create_group_in_background in tasks.py."""
    return mocker.patch("imperial_coldfront_plugin.tasks.ldap_create_group")


@pytest.fixture(autouse=True)
def ldap_add_member_mock(mocker):
    """Mock ldap_add_member_to_group_in_background in tasks.py."""
    return mocker.patch("imperial_coldfront_plugin.signals.ldap_add_member_to_group")


@pytest.fixture(autouse=True)
def ldap_delete_group_mock(mocker):
    """Mock ldap_delete_group_in_background in tasks.py."""
    return mocker.patch("imperial_coldfront_plugin.tasks.ldap_delete_group")


@pytest.fixture(autouse=True)
def ldap_gid_in_use_mock(mocker):
    """Mock ldap_gid_in_use in tasks.py."""
    return mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_gid_in_use",
        return_value=False,
    )


@pytest.fixture
def rdf_form_data(project, settings):
    """Fixture to provide RDFAllocationForm data."""
    faculty_id = "foe"
    department_id = settings.DEPARTMENTS_IN_FACULTY[faculty_id][0]
    return dict(
        project=project.pk,
        faculty=faculty_id,
        department=department_id,
        start_date=datetime.now().date(),
        end_date=datetime.max.date(),
        size=10,
        allocation_shortname="shorty",
        description="The allocation description",
    )


def test_create_rdf_allocation(
    gpfs_create_fileset_mock,
    ldap_create_group_mock,
    ldap_add_member_mock,
    project,
    rdf_allocation_dependencies,
    rdf_allocation_shortname,
    rdf_allocation_ldap_name,
    settings,
    rdf_form_data,
    enable_ldap,
):
    """Test create_rdf_allocation task."""
    # set all of these so they are not empty
    settings.GPFS_FILESYSTEM_NAME = "fsname"
    settings.GPFS_FILESYSTEM_MOUNT_PATH = "/mountpath"
    settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES = "top/level"

    # get some metadata from the project level
    faculty = project.projectattribute_set.get(proj_attr_type__name="Faculty").value
    department = project.projectattribute_set.get(
        proj_attr_type__name="Department"
    ).value
    group_id = project.projectattribute_set.get(proj_attr_type__name="Group ID").value
    fileset_path_info = FilesetPathInfo(
        settings.GPFS_FILESYSTEM_MOUNT_PATH,
        settings.GPFS_FILESYSTEM_NAME,
        settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES,
        faculty,
        department,
        group_id,
        rdf_allocation_shortname,
    )

    gid = get_new_gid()

    form = RDFAllocationForm(data=rdf_form_data)
    assert form.is_valid(), f"Form errors: {form.errors}"
    allocation = create_rdf_allocation(form.cleaned_data)

    start_date = rdf_form_data["start_date"]
    end_date = rdf_form_data["end_date"]
    description = rdf_form_data["description"]
    size = rdf_form_data["size"]
    allocation = Allocation.objects.get(
        project=project,
        status__name="Active",
        quantity=1,
        start_date=start_date,
        end_date=end_date,
        justification=description,
    )
    storage_attribute = AllocationAttribute.objects.get(
        allocation_attribute_type__name="Storage Quota (TB)",
        allocation=allocation,
        value=size,
    )
    AllocationAttributeUsage.objects.get(
        allocation_attribute=storage_attribute, value=0
    )
    files_attribute = AllocationAttribute.objects.get(
        allocation_attribute_type__name="Files Quota",
        allocation=allocation,
        value=settings.GPFS_FILES_QUOTA,
    )
    AllocationAttributeUsage.objects.get(allocation_attribute=files_attribute, value=0)
    AllocationAttribute.objects.get(
        allocation_attribute_type__name="Shortname",
        allocation=allocation,
        value=rdf_allocation_shortname,
    )
    AllocationAttribute.objects.get(
        allocation_attribute_type__name="Filesystem location",
        allocation=allocation,
        value=str(fileset_path_info.fileset_absolute_path),
    )
    AllocationUser.objects.get(
        allocation=allocation, user=project.pi, status__name="Active"
    )
    ldap_create_group_mock.assert_called_once_with(rdf_allocation_ldap_name, gid)
    ldap_add_member_mock.assert_called_once_with(
        rdf_allocation_ldap_name, project.pi.username, allow_already_present=True
    )

    gpfs_create_fileset_mock.assert_called_once_with(
        fileset_path_info=fileset_path_info,
        owner_id="root",
        group_id=rdf_allocation_ldap_name,
        fileset_posix_permissions=settings.GPFS_FILESET_POSIX_PERMISSIONS,
        fileset_acl=settings.GPFS_FILESET_ACL,
        parent_posix_permissions=settings.GPFS_PARENT_DIRECTORY_POSIX_PERMISSIONS,
        parent_acl=settings.GPFS_PARENT_DIRECTORY_ACL,
        block_quota=f"{size}T",
        files_quota=settings.GPFS_FILES_QUOTA,
        logger=logging.getLogger("django-q"),
    )


def test_create_rdf_allocation_ldap_rollback(
    gpfs_create_fileset_mock,
    ldap_create_group_mock,
    ldap_add_member_mock,
    project,
    rdf_allocation_dependencies,
    rdf_allocation_shortname,
    rdf_allocation_ldap_name,
    settings,
    rdf_form_data,
    enable_ldap,
):
    """Test create_rdf_allocation task rolls back on LDAP error."""
    # first ldap call now raises an error
    ldap_create_group_mock.side_effect = RuntimeError("oh no!")

    form = RDFAllocationForm(data=rdf_form_data)
    assert form.is_valid(), f"Form errors: {form.errors}"
    with pytest.raises(RuntimeError):
        create_rdf_allocation(form.cleaned_data)

    # check initial database actions have been rolled back
    assert not Allocation.objects.all()


def test_create_rdf_allocation_gpfs_rollback(
    gpfs_create_fileset_mock,
    ldap_create_group_mock,
    ldap_add_member_mock,
    ldap_delete_group_mock,
    project,
    rdf_allocation_dependencies,
    rdf_allocation_shortname,
    rdf_allocation_ldap_name,
    settings,
    rdf_form_data,
    enable_ldap,
):
    """Test create_rdf_allocation task rolls back on GPFS error."""
    # first gpfs call now raises an error
    gpfs_create_fileset_mock.side_effect = RuntimeError("oh no!")
    gid = get_new_gid()
    form = RDFAllocationForm(data=rdf_form_data)
    assert form.is_valid(), f"Form errors: {form.errors}"
    with pytest.raises(RuntimeError):
        create_rdf_allocation(form.cleaned_data)

    # check initial database actions have been rolled back
    assert not Allocation.objects.all()

    # check ldap group was created then deleted
    ldap_create_group_mock.assert_called_once_with(rdf_allocation_ldap_name, gid)
    ldap_delete_group_mock.assert_called_once_with(
        rdf_allocation_ldap_name, allow_missing=True
    )


@pytest.fixture
def ldap_group_search_mock(mocker):
    """Mock the ldap Connection search method."""
    return mocker.patch("imperial_coldfront_plugin.tasks.ldap_group_member_search")


@pytest.fixture
def notify_mock(mocker):
    """Mock the send_discrepancy_notification function in tasks.py."""
    return mocker.patch("imperial_coldfront_plugin.tasks.send_discrepancy_notification")


def test_check_ldap_consistency_no_discrepancies(
    rdf_allocation,
    allocation_user,
    ldap_group_search_mock,
    notify_mock,
    rdf_allocation_ldap_name,
):
    """Test when everything is in sync between Coldfront and AD."""
    username = allocation_user.user.username
    ldap_group_search_mock.return_value = {rdf_allocation_ldap_name: [username]}

    result = check_ldap_consistency()

    assert result == []
    notify_mock.assert_not_called()


def test_check_ldap_consistency_missing_members(
    rdf_allocation,
    allocation_user,
    ldap_group_search_mock,
    notify_mock,
    rdf_allocation_ldap_name,
    enable_ldap,
):
    """Test when a user is missing from AD group."""
    username = allocation_user.user.username
    ldap_group_search_mock.return_value = {rdf_allocation_ldap_name: []}

    result = check_ldap_consistency()

    assert len(result) == 1
    discrepancy = result[0]
    assert discrepancy["allocation_id"] == rdf_allocation.id
    assert discrepancy["group_name"] == rdf_allocation_ldap_name
    assert discrepancy["project_name"] == rdf_allocation.project.title
    assert username in discrepancy["missing_members"]
    assert not discrepancy["extra_members"]

    notify_mock.assert_called_once()


def test_check_ldap_consistency_extra_members(
    rdf_allocation,
    allocation_user,
    ldap_group_search_mock,
    notify_mock,
    rdf_allocation_ldap_name,
    enable_ldap,
):
    """Test when there are extra users in AD group."""
    username = allocation_user.user.username
    extra_user = "extra_user"
    ldap_group_search_mock.return_value = {
        rdf_allocation_ldap_name: [username, extra_user]
    }

    result = check_ldap_consistency()

    assert len(result) == 1
    discrepancy = result[0]
    assert discrepancy["allocation_id"] == rdf_allocation.id
    assert discrepancy["group_name"] == rdf_allocation_ldap_name
    assert not discrepancy["missing_members"]
    assert extra_user in discrepancy["extra_members"]

    notify_mock.assert_called_once()
