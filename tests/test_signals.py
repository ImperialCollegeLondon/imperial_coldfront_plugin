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
):
    """Test sync_ldap_group_membership signal."""
    # clear mock calls from setup
    ldap_add_member_mock.reset_mock()
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


def test_remove_ldap_group_membership(
    ldap_remove_member_mock,
    rdf_allocation_shortname,
    allocation_user,
    user,
    settings,
):
    """Test remove_ldap_group_membership signal."""
    ldap_remove_member_mock.assert_not_called()

    allocation_user.delete()

    ldap_remove_member_mock.assert_called_once_with(
        f"{settings.LDAP_RDF_SHORTNAME_PREFIX}{rdf_allocation_shortname}",
        user.username,
        allow_missing=True,
    )


def test_remove_ldap_group_membership_non_rdf_allocation(
    ldap_remove_member_mock, allocation_user_active_status, project, user
):
    """Test remove_ldap_group_membership_signal for non-rdf allocation."""
    active_allocation_status, _ = AllocationStatusChoice.objects.get_or_create(
        name="Active"
    )
    allocation = Allocation.objects.create(
        project=project,
        status=active_allocation_status,
    )
    allocation_user = AllocationUser.objects.create(
        allocation=allocation,
        user=user,
        status=allocation_user_active_status,
    )

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
):
    """Test that task is not called when allocation is active."""
    remove_allocation_group_members_mock.assert_not_called()

    # Allocation is already active, so saving shouldn't trigger the task
    rdf_allocation.save()

    remove_allocation_group_members_mock.assert_not_called()


def test_remove_ldap_group_members_non_rdf_allocation(
    remove_allocation_group_members_mock,
    project,
    user,
    allocation_user_active_status,
):
    """Test that task is not called for non rdf allocations."""
    allocation_inactive_status = AllocationStatusChoice.objects.create(name="Inactive")
    active_allocation_status, _ = AllocationStatusChoice.objects.get_or_create(
        name="Active"
    )
    allocation = Allocation.objects.create(
        project=project,
        status=active_allocation_status,
    )
    AllocationUser.objects.create(
        allocation=allocation,
        user=user,
        status=allocation_user_active_status,
    )
    allocation.status = allocation_inactive_status
    allocation.save()
    remove_allocation_group_members_mock.assert_not_called()


def test_remove_ldap_group_members_ldap_disabled(
    remove_allocation_group_members_mock, rdf_allocation, settings
):
    """Test that task is not called when LDAP is disabled."""
    settings.LDAP_ENABLED = False
    allocation_inactive_status = AllocationStatusChoice.objects.create(name="Inactive")
    rdf_allocation.status = allocation_inactive_status
    rdf_allocation.save()

    remove_allocation_group_members_mock.assert_not_called()


@pytest.fixture
def zero_quota_mock(mocker):
    """Mock zero_allocation_gpfs_quota task."""
    return mocker.patch("imperial_coldfront_plugin.tasks.zero_allocation_gpfs_quota")


def test_allocation_expired_handler_triggers_task(rdf_allocation, zero_quota_mock):
    """Test that changing allocation status to Expired spawns the quota zeroing task."""
    expired_status = AllocationStatusChoice.objects.create(name="Expired")
    rdf_allocation.status = expired_status
    rdf_allocation.save()
    zero_quota_mock.assert_called_once_with(rdf_allocation.pk)


def test_allocation_expired_handler_does_not_trigger_for_other_statuses(
    rdf_allocation, rdf_allocation_gid, zero_quota_mock
):
    """Test that changing to a non-Expired status does not trigger the task."""
    removed_status = AllocationStatusChoice.objects.create(name="Removed")
    rdf_allocation.status = removed_status
    rdf_allocation.save()
    zero_quota_mock.assert_not_called()


def test_allocation_expired_handler_skips_new_allocations(
    project,
    remove_allocation_group_members_mock,
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

    remove_allocation_group_members_mock.assert_not_called()


def test_allocation_expired_handler_skips_non_rdf_active_allocation(
    project, zero_quota_mock
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

    zero_quota_mock.assert_not_called()


def test_sync_ldap_group_membership_non_rdf_allocation(
    ldap_remove_member_mock,
    ldap_add_member_mock,
    user,
    allocation_user_active_status,
    project,
):
    """Test sync_ldap_group_membership signal does not apply to non-RDF allocations."""
    active_allocation_status, _ = AllocationStatusChoice.objects.get_or_create(
        name="Active"
    )
    allocation_user_inactive_status = AllocationUserStatusChoice.objects.create(
        name="Inactive"
    )
    allocation = Allocation.objects.create(
        project=project,
        status=active_allocation_status,
    )
    allocation_user = AllocationUser.objects.create(
        allocation=allocation,
        user=user,
        status=allocation_user_active_status,
    )

    ldap_add_member_mock.assert_not_called()
    ldap_remove_member_mock.assert_not_called()

    allocation_user.status = allocation_user_inactive_status
    allocation_user.save()

    ldap_add_member_mock.assert_not_called()
    ldap_remove_member_mock.assert_not_called()
