import pytest
from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
    AllocationStatusChoice,
    AllocationUser,
    AllocationUserStatusChoice,
)
from coldfront.core.resource.models import Resource, ResourceType


@pytest.fixture
def ldap_add_member_mock(mocker):
    """Mock ldap_add_member_to_group_in_background in signals.py."""
    return mocker.patch("imperial_coldfront_plugin.signals.ldap_add_member_to_group")


@pytest.fixture
def ldap_remove_member_mock(mocker):
    """Mock ldap_remove_member_from_group_in_background in signals.py."""
    return mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_remove_member_from_group",
    )


@pytest.fixture
def ldap_gid_in_use_mock(mocker):
    """Mock ldap_gid_in_use in signals.py."""
    return mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_gid_in_use",
        return_value=False,
    )


@pytest.fixture
def remove_allocation_group_members_mock(mocker):
    """Mock remove_allocation_group_members task in signals.py."""
    return mocker.patch(
        "imperial_coldfront_plugin.tasks.remove_allocation_group_members"
    )


def test_sync_ldap_group_membership(
    ldap_remove_member_mock,
    ldap_add_member_mock,
    user,
    rdf_allocation_ldap_name,
    allocation_user,
    enable_ldap,
):
    """Test sync_ldap_group_membership signal."""
    ldap_add_member_mock.assert_not_called()
    ldap_remove_member_mock.assert_not_called()

    allocation_user_inactive_status = AllocationUserStatusChoice.objects.create(
        name="Inactive"
    )
    allocation_user.status = allocation_user_inactive_status
    allocation_user.save()

    ldap_add_member_mock.assert_not_called()
    ldap_remove_member_mock.assert_called_once_with(
        rdf_allocation_ldap_name, user.username, allow_missing=True
    )


def test_sync_ldap_group_membership_no_project_id(
    ldap_remove_member_mock,
    ldap_add_member_mock,
    user,
    rdf_allocation,
    rdf_allocation_shortname,
    allocation_user_active_status,
):
    """Test sync_ldap_group_membership signal for non-rdf allocations."""
    rdf_allocation.allocationattribute_set.get(
        allocation_attribute_type__name="Shortname"
    ).delete()
    allocation_user = AllocationUser.objects.create(
        allocation=rdf_allocation,
        user=user,
        status=allocation_user_active_status,
    )

    ldap_add_member_mock.assert_not_called()
    ldap_remove_member_mock.assert_not_called()

    allocation_user.delete()

    ldap_add_member_mock.assert_not_called()
    ldap_remove_member_mock.assert_not_called()


def test_remove_ldap_group_membership(
    ldap_remove_member_mock,
    rdf_allocation_shortname,
    allocation_user,
    user,
    enable_ldap,
):
    """Test remove_ldap_group_membership signal."""
    ldap_remove_member_mock.assert_not_called()

    allocation_user.delete()

    ldap_remove_member_mock.assert_called_once_with(
        f"rdf-{rdf_allocation_shortname}", user.username, allow_missing=True
    )


def test_remove_ldap_group_membership_no_shortname(
    ldap_remove_member_mock, rdf_allocation, allocation_user
):
    """Test remove_ldap_group_membership_signal for non-rdf allocation."""
    rdf_allocation.allocationattribute_set.get(
        allocation_attribute_type__name="Shortname"
    ).delete()
    allocation_user.delete()
    ldap_remove_member_mock.assert_not_called()


def test_ensure_unique_shortname(rdf_allocation, rdf_allocation_shortname):
    """Test creating a second allocation with the same shortname raises an error."""
    from coldfront.core.allocation.models import (
        AllocationAttribute,
        AllocationAttributeType,
    )

    shortname_attribute_type = AllocationAttributeType.objects.get(name="Shortname")
    with pytest.raises(ValueError):
        AllocationAttribute.objects.create(
            allocation_attribute_type=shortname_attribute_type,
            allocation=rdf_allocation,
            value=rdf_allocation_shortname,
        )
    # check there is still only one allocation with the shortname
    assert AllocationAttribute.objects.get(
        allocation_attribute_type=shortname_attribute_type,
        value=rdf_allocation_shortname,
    )


def test_ensure_unique_group_id(project):
    """Test creating a second project with the same Group ID raises an error."""
    from coldfront.core.project.models import (
        ProjectAttribute,
        ProjectAttributeType,
    )

    group_id_attribute_type = ProjectAttributeType.objects.get(name="Group ID")
    with pytest.raises(ValueError):
        ProjectAttribute.objects.create(
            proj_attr_type=group_id_attribute_type,
            project=project,
            value=project.pi.username,
        )
    # check there is still only one group id with the shortname
    assert ProjectAttribute.objects.get(
        proj_attr_type=group_id_attribute_type,
        value=project.pi.username,
    )


def test_ensure_no_existing_gid_database(rdf_allocation, rdf_allocation_gid):
    """Test creating a project with an existing GID in the database raises an error."""
    gid_attribute_type = AllocationAttributeType.objects.get(name="GID")
    with pytest.raises(ValueError):
        AllocationAttribute.objects.create(
            allocation_attribute_type=gid_attribute_type,
            allocation=rdf_allocation,
            value=rdf_allocation_gid,
        )


def test_ensure_no_existing_gid_ldap(
    rdf_allocation,
    rdf_allocation_gid,
    ldap_gid_in_use_mock,
):
    """Test creating a project with an existing GID in LDAP raises an error."""
    ldap_gid_in_use_mock.return_value = True
    gid_attribute_type = AllocationAttributeType.objects.get(name="GID")
    with pytest.raises(ValueError):
        AllocationAttribute.objects.create(
            allocation_attribute_type=gid_attribute_type,
            allocation=rdf_allocation,
            value=rdf_allocation_gid,
        )


def test_remove_ldap_group_members_if_allocation_inactive(
    remove_allocation_group_members_mock,
    rdf_allocation,
    allocation_user,
    enable_ldap,
):
    """Test remove_ldap_group_members_if_allocation_inactive signal."""
    remove_allocation_group_members_mock.assert_not_called()

    # Change allocation status to inactive
    allocation_inactive_status = AllocationStatusChoice.objects.create(name="Inactive")
    rdf_allocation.status = allocation_inactive_status
    rdf_allocation.save()

    remove_allocation_group_members_mock.assert_called_once_with(rdf_allocation.pk)


def test_remove_ldap_group_members_if_allocation_active(
    remove_allocation_group_members_mock,
    rdf_allocation,
    allocation_user,
    enable_ldap,
):
    """Test that task is not called when allocation is active."""
    remove_allocation_group_members_mock.assert_not_called()

    # Allocation is already active, so saving shouldn't trigger the task
    rdf_allocation.save()

    remove_allocation_group_members_mock.assert_not_called()


def test_remove_ldap_group_members_no_shortname(
    remove_allocation_group_members_mock,
    rdf_allocation,
    enable_ldap,
):
    """Test that task is not called when allocation has no shortname."""
    rdf_allocation.allocationattribute_set.get(
        allocation_attribute_type__name="Shortname"
    ).delete()

    allocation_inactive_status = AllocationStatusChoice.objects.create(name="Inactive")
    rdf_allocation.status = allocation_inactive_status
    rdf_allocation.save()

    remove_allocation_group_members_mock.assert_not_called()


def test_remove_ldap_group_members_ldap_disabled(
    remove_allocation_group_members_mock,
    rdf_allocation,
):
    """Test that task is not called when LDAP is disabled."""
    allocation_inactive_status = AllocationStatusChoice.objects.create(name="Inactive")
    rdf_allocation.status = allocation_inactive_status
    rdf_allocation.save()

    remove_allocation_group_members_mock.assert_not_called()


@pytest.fixture
def async_task_mock(mocker):
    """Mock async_task from django_q.tasks."""
    mock = mocker.patch("imperial_coldfront_plugin.signals.async_task")
    mock.assert_not_called()
    return mock


def test_allocation_expired_handler_triggers_task(
    async_task_mock,
    rdf_allocation,
):
    """Test that changing allocation status to Expired spawns the quota zeroing task."""
    expired_status = AllocationStatusChoice.objects.create(name="Expired")
    rdf_allocation.status = expired_status
    rdf_allocation.save()

    async_task_mock.assert_called_once_with(
        "imperial_coldfront_plugin.tasks.zero_allocation_gpfs_quota",
        rdf_allocation.pk,
    )


def test_allocation_expired_handler_does_not_trigger_for_other_statuses(
    async_task_mock,
    rdf_allocation,
):
    """Test that changing to a non-Expired status does not trigger the task."""
    removed_status = AllocationStatusChoice.objects.create(name="Removed")
    rdf_allocation.status = removed_status
    rdf_allocation.save()

    async_task_mock.assert_not_called()


def test_allocation_expired_handler_skips_new_allocations(
    async_task_mock,
    project,
):
    """Test that creating a new allocation does not trigger the task (pk is None)."""
    expired_status = AllocationStatusChoice.objects.create(name="Expired")
    rdf_resource = Resource.objects.filter(name__icontains="RDF").first()

    allocation = Allocation(
        project=project,
        status=expired_status,
    )
    allocation.save()
    if rdf_resource:
        allocation.resources.add(rdf_resource)

    async_task_mock.assert_not_called()


def test_allocation_expired_handler_skips_non_rdf_active_allocation(
    async_task_mock,
    project,
):
    """Test that expiring an allocation without the 'RDF Active' resource does not trigger the task."""  # noqa E501
    active_status, _ = AllocationStatusChoice.objects.get_or_create(name="Active")
    expired_status, _ = AllocationStatusChoice.objects.get_or_create(name="Expired")

    resource_type = ResourceType.objects.first()
    other_resource = Resource.objects.create(
        name="Other Storage",
        resource_type=resource_type,
    )

    allocation = Allocation.objects.create(project=project, status=active_status)
    allocation.resources.add(other_resource)

    allocation.status = expired_status
    allocation.save()

    async_task_mock.assert_not_called()
