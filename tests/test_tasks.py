import logging
from datetime import datetime, timedelta

import pytest
from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeUsage,
    AllocationStatusChoice,
    AllocationUser,
)
from coldfront.core.resource.models import Resource
from django.conf import settings
from django.utils import timezone

from imperial_coldfront_plugin.forms import RDFAllocationForm
from imperial_coldfront_plugin.gid import get_new_gid
from imperial_coldfront_plugin.gpfs_client import FilesetPathInfo
from imperial_coldfront_plugin.tasks import (
    check_ldap_consistency,
    check_rdf_allocation_expiry_notifications,
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
def ldap_remove_member_mock(mocker):
    """Mock ldap_remove_member_from_group in tasks.py."""
    return mocker.patch("imperial_coldfront_plugin.ldap.ldap_remove_member_from_group")


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


@pytest.fixture
def send_expiry_warning_mock(mocker):
    """Mock send_allocation_expiry_warning."""
    return mocker.patch(
        "imperial_coldfront_plugin.tasks.send_allocation_expiry_warning"
    )


@pytest.fixture
def send_removal_warning_mock(mocker):
    """Mock send_allocation_removal_warning."""
    return mocker.patch(
        "imperial_coldfront_plugin.tasks.send_allocation_removal_warning"
    )


@pytest.fixture
def send_deletion_warning_mock(mocker):
    """Mock send_allocation_deletion_warning."""
    return mocker.patch(
        "imperial_coldfront_plugin.tasks.send_allocation_deletion_warning"
    )


@pytest.fixture
def send_deletion_notification_mock(mocker):
    """Mock send_allocation_deletion_notification."""
    return mocker.patch(
        "imperial_coldfront_plugin.tasks.send_allocation_deletion_notification"
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


def test_remove_allocation_group_members(
    ldap_remove_member_mock,
    rdf_allocation,
    allocation_user,
    rdf_allocation_ldap_name,
    enable_ldap,
):
    """Test _remove_allocation_group_members removes all active users."""
    from imperial_coldfront_plugin.tasks import remove_allocation_group_members

    username = allocation_user.user.username

    remove_allocation_group_members(rdf_allocation.pk)

    ldap_remove_member_mock.assert_called_once_with(
        rdf_allocation_ldap_name,
        username,
        allow_missing=True,
    )


def test_remove_allocation_group_members_multiple_users(
    ldap_remove_member_mock,
    rdf_allocation,
    allocation_user,
    allocation_user_active_status,
    user_factory,
    rdf_allocation_ldap_name,
    enable_ldap,
):
    """Test _remove_allocation_group_members removes multiple active users."""
    from imperial_coldfront_plugin.tasks import remove_allocation_group_members

    # Create additional active users
    user2 = user_factory()
    user3 = user_factory()

    allocation_user2 = AllocationUser.objects.create(  # noqa F841
        allocation=rdf_allocation,
        user=user2,
        status=allocation_user_active_status,
    )
    allocation_user3 = AllocationUser.objects.create(  # noqa F841
        allocation=rdf_allocation,
        user=user3,
        status=allocation_user_active_status,
    )

    remove_allocation_group_members(rdf_allocation.pk)

    assert ldap_remove_member_mock.call_count == 3
    ldap_remove_member_mock.assert_any_call(
        rdf_allocation_ldap_name,
        allocation_user.user.username,
        allow_missing=True,
    )
    ldap_remove_member_mock.assert_any_call(
        rdf_allocation_ldap_name,
        user2.username,
        allow_missing=True,
    )
    ldap_remove_member_mock.assert_any_call(
        rdf_allocation_ldap_name,
        user3.username,
        allow_missing=True,
    )


def test_remove_allocation_group_members_no_shortname(
    ldap_remove_member_mock,
    rdf_allocation,
    allocation_user,
):
    """Test _remove_allocation_group_members handles missing shortname gracefully."""
    from imperial_coldfront_plugin.tasks import remove_allocation_group_members

    # Remove the shortname attribute
    rdf_allocation.allocationattribute_set.get(
        allocation_attribute_type__name="Shortname"
    ).delete()

    remove_allocation_group_members(rdf_allocation.pk)

    ldap_remove_member_mock.assert_not_called()


@pytest.mark.parametrize(
    "days_offset, expected_status_name",
    [
        # Expired past deletion threshold
        (-(settings.RDF_ALLOCATION_EXPIRY_DELETION_DAYS + 1), "Deleted"),
        # Expired past removal threshold
        (-(settings.RDF_ALLOCATION_EXPIRY_REMOVAL_DAYS + 1), "Removed"),
        # Not expired
        (0, "Active"),
    ],
)
def test_check_allocation_status(
    rdf_allocation,
    enable_ldap,
    days_offset,
    expected_status_name,
):
    """Test mark_expired_allocations_as_deleted functionality."""
    from imperial_coldfront_plugin.tasks import check_allocation_status

    # Test that expired allocations are changed to "Deleted":
    expected_status = AllocationStatusChoice.objects.get(name=expected_status_name)
    rdf_allocation.end_date = timezone.now() + timedelta(days=days_offset)
    rdf_allocation.save()

    check_allocation_status()
    rdf_allocation.refresh_from_db()
    assert rdf_allocation.status == expected_status


def test_check_expiry_notifications_expiry_warning(
    rdf_allocation,
    send_expiry_warning_mock,
    send_removal_warning_mock,
    send_deletion_warning_mock,
    send_deletion_notification_mock,
    settings,
):
    """Test expiry warning is sent at scheduled intervals."""
    # Set allocation to expire in 90 days
    days_before_expiry = settings.RDF_ALLOCATION_EXPIRY_WARNING_SCHEDULE[0]
    rdf_allocation.end_date = datetime.now().date() + timedelta(days=days_before_expiry)
    rdf_allocation.save()

    check_rdf_allocation_expiry_notifications()

    send_expiry_warning_mock.assert_called_once_with(
        rdf_allocation.pk, rdf_allocation.project.pi.email, 90
    )
    send_removal_warning_mock.assert_not_called()
    send_deletion_warning_mock.assert_not_called()
    send_deletion_notification_mock.assert_not_called()


def test_check_expiry_notifications_removal_warning(
    rdf_allocation,
    send_expiry_warning_mock,
    send_removal_warning_mock,
    send_deletion_warning_mock,
    send_deletion_notification_mock,
):
    """Test removal warning is sent on expiry day."""
    # Set allocation to expire today
    rdf_allocation.end_date = datetime.now().date()
    rdf_allocation.save()

    check_rdf_allocation_expiry_notifications()

    send_removal_warning_mock.assert_called_once_with(
        rdf_allocation.pk, rdf_allocation.project.pi.email, 0
    )
    send_expiry_warning_mock.assert_not_called()
    send_deletion_warning_mock.assert_not_called()
    send_deletion_notification_mock.assert_not_called()


def test_check_expiry_notifications_deletion_warning(
    rdf_allocation,
    send_expiry_warning_mock,
    send_removal_warning_mock,
    send_deletion_warning_mock,
    send_deletion_notification_mock,
    settings,
):
    """Test deletion warning is sent after expiry."""
    # Set allocation to have expired 7 days ago
    days_after_expiry = abs(settings.RDF_ALLOCATION_DELETION_WARNING_SCHEDULE[0])
    rdf_allocation.end_date = datetime.now().date() - timedelta(days=days_after_expiry)
    rdf_allocation.save()

    check_rdf_allocation_expiry_notifications()

    send_deletion_warning_mock.assert_called_once_with(
        rdf_allocation.pk, rdf_allocation.project.pi.email, -days_after_expiry
    )
    send_expiry_warning_mock.assert_not_called()
    send_removal_warning_mock.assert_not_called()
    send_deletion_notification_mock.assert_not_called()


def test_check_expiry_notifications_deletion_notification(
    rdf_allocation,
    send_expiry_warning_mock,
    send_removal_warning_mock,
    send_deletion_warning_mock,
    send_deletion_notification_mock,
    settings,
):
    """Test deletion notification is sent 14 days after expiry."""
    # Set allocation to have expired per deletion notification schedule
    days_after_expiry = abs(settings.RDF_ALLOCATION_DELETION_NOTIFICATION_SCHEDULE[0])
    rdf_allocation.end_date = datetime.now().date() - timedelta(days=days_after_expiry)
    rdf_allocation.save()

    check_rdf_allocation_expiry_notifications()

    send_deletion_notification_mock.assert_called_once_with(
        rdf_allocation.pk, rdf_allocation.project.pi.email
    )
    send_expiry_warning_mock.assert_not_called()
    send_removal_warning_mock.assert_not_called()
    send_deletion_warning_mock.assert_not_called()


def test_check_expiry_notifications_no_end_date(
    rdf_allocation,
    send_expiry_warning_mock,
):
    """Test notification skipped when allocation has no end date."""
    # Remove end date
    rdf_allocation.end_date = None
    rdf_allocation.save()

    check_rdf_allocation_expiry_notifications()

    send_expiry_warning_mock.assert_not_called()


def test_check_expiry_notifications_multiple_allocations(
    rdf_allocation,
    rdf_allocation_dependencies,
    project,
    send_expiry_warning_mock,
    send_removal_warning_mock,
    settings,
):
    """Test notifications sent for multiple allocations with different schedules."""
    # Get the required objects
    allocation_active_status = AllocationStatusChoice.objects.get(name="Active")
    rdf_resource = Resource.objects.get(name="RDF Active")

    # First allocation expires per expiry warning schedule (e.g., 30 days)
    days_before_expiry = settings.RDF_ALLOCATION_EXPIRY_WARNING_SCHEDULE[2]  # 30 days
    rdf_allocation.end_date = datetime.now().date() + timedelta(days=days_before_expiry)
    rdf_allocation.save()

    # Create second allocation per removal warning schedule (e.g., -3 days)
    days_after_expiry = abs(settings.RDF_ALLOCATION_REMOVAL_WARNING_SCHEDULE[1])  # -3
    allocation2 = Allocation.objects.create(
        project=project,
        status=allocation_active_status,
        end_date=datetime.now().date() - timedelta(days=days_after_expiry),
    )
    allocation2.resources.add(rdf_resource)

    check_rdf_allocation_expiry_notifications()

    send_expiry_warning_mock.assert_called_once_with(
        rdf_allocation.pk, rdf_allocation.project.pi.email, days_before_expiry
    )
    send_removal_warning_mock.assert_called_once_with(
        allocation2.pk, project.pi.email, -days_after_expiry
    )
