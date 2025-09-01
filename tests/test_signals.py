import pytest
from coldfront.core.allocation.models import AllocationUser, AllocationUserStatusChoice


@pytest.fixture
def ldap_add_member_mock(mocker):
    """Mock ldap_add_member_to_group_in_background in signals.py."""
    return mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_add_member_to_group_in_background"
    )


@pytest.fixture
def ldap_remove_member_mock(mocker):
    """Mock ldap_remove_member_from_group_in_background in signals.py."""
    return mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_remove_member_from_group_in_background"
    )


def test_sync_ldap_group_membership(
    ldap_remove_member_mock,
    ldap_add_member_mock,
    user,
    rdf_allocation_ldap_name,
    allocation_user,
):
    """Test sync_ldap_group_membership signal."""
    ldap_add_member_mock.assert_called_once_with(
        rdf_allocation_ldap_name, user.username, allow_already_present=True
    )
    ldap_remove_member_mock.assert_not_called()

    allocation_user_inactive_status = AllocationUserStatusChoice.objects.create(
        name="Inactive"
    )
    allocation_user.status = allocation_user_inactive_status
    allocation_user.save()

    ldap_add_member_mock.assert_called_once()
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
):
    """Test remove_ldap_group_membership signal."""
    ldap_remove_member_mock.assert_not_called()

    allocation_user.delete()

    ldap_remove_member_mock(
        f"rdf-{rdf_allocation_shortname}", user.username, allowing_missing=True
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
