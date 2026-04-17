from unittest.mock import call

import pytest
from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
    AllocationStatusChoice,
    AllocationUser,
    AllocationUserStatusChoice,
    Resource,
)

from imperial_coldfront_plugin.models import HX2Allocation, RDFAllocation


@pytest.fixture
def ldap_add_member_mock(mocker):
    """Mock ldap_add_member_to_group_in_background in signals.py."""
    return mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_add_member_to_group", autospec=True
    )


@pytest.fixture
def ldap_remove_member_mock(mocker):
    """Mock ldap_remove_member_from_group_in_background in signals.py."""
    return mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_remove_member_from_group", autospec=True
    )


@pytest.fixture
def ldap_gid_in_use_mock(mocker):
    """Mock ldap_gid_in_use in signals.py."""
    return mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_gid_in_use",
        return_value=False,
        autospec=True,
    )


@pytest.fixture
def remove_ldap_group_members_mock(mocker):
    """Mock remove_ldap_group_members task in signals.py."""
    return mocker.patch(
        "imperial_coldfront_plugin.signals.remove_ldap_group_members",
    )


class TestAllocationAttributeEnsureNoExistingGID:
    """Tests for allocation_attribute_ensure_no_existing_gid signal handler."""

    @pytest.fixture
    def gid_attribute_type(self, db):
        """Fixture to create a GID AllocationAttributeType."""
        return AllocationAttributeType.objects.get(name="GID")

    def test_success(self, rdf_allocation):
        """Test creating a project with a unique GID succeeds."""
        # signal is triggered by rdf_allocation fixture creation

    def test_ldap_disabled(
        self, settings, gid_attribute_type, rdf_allocation, ldap_gid_in_use_mock
    ):
        """Test that LDAP is not checked when disabled."""
        settings.LDAP_ENABLED = False
        ldap_gid_in_use_mock.return_value = True
        # should not raise an error because LDAP is disabled
        AllocationAttribute.objects.create(
            allocation_attribute_type=gid_attribute_type,
            allocation=rdf_allocation,
            value=123,
        )

    def test_existing_gid_database(
        self, rdf_allocation, rdf_allocation_gid, gid_attribute_type
    ):
        """Test creating a project with GID existing in the database raises an error."""
        with pytest.raises(ValueError):
            AllocationAttribute.objects.create(
                allocation_attribute_type=gid_attribute_type,
                allocation=rdf_allocation,
                value=rdf_allocation_gid,
            )

    def test_existing_gid_ldap(
        self,
        rdf_allocation,
        rdf_allocation_gid,
        ldap_gid_in_use_mock,
        gid_attribute_type,
    ):
        """Test creating a project with an existing GID in LDAP raises an error."""
        ldap_gid_in_use_mock.return_value = True
        with pytest.raises(ValueError):
            AllocationAttribute.objects.create(
                allocation_attribute_type=gid_attribute_type,
                allocation=rdf_allocation,
                value=rdf_allocation_gid,
            )


class TestAllocationAttributeEnsureUniqueShortname:
    """Tests for allocation_attribute_ensure_unique_shortname signal handler."""

    def test_success(self, rdf_allocation):
        """Test creating a project with a unique shortname succeeds."""
        # signal is triggered by rdf_allocation fixture creation

    def test_ensure_unique_shortname(self, rdf_allocation, rdf_allocation_shortname):
        """Test creating a second allocation with the same shortname raises an error."""
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


class TestProjectAttributeEnsureUniqueGroupID:
    """Tests for project_attribute_ensure_unique_group_id signal handler."""

    def test_success(self, project):
        """Test creating a project with a unique group ID succeeds."""
        # signal is triggered by project fixture creation

    def test_ensure_unique_group_id(self, project, user):
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
        # check there is still only one group id with the value
        assert ProjectAttribute.objects.get(
            proj_attr_type=group_id_attribute_type,
            value=project.pi.username,
        )


@pytest.fixture
def allocation_active_status(db):
    """Fixture to create an Active AllocationStatusChoice."""
    return AllocationStatusChoice.objects.get_or_create(name="Active")[0]


@pytest.fixture
def allocation_inactive_status(db):
    """Fixture to create an Inactive AllocationStatusChoice."""
    return AllocationStatusChoice.objects.get_or_create(name="Inactive")[0]


class TestAllocationUserSyncLDAPGroupMembership:
    """Tests for allocation_user_sync_ldap_group_membership signal handler."""

    @pytest.fixture
    def allocation(self, rdf_or_hx2_allocation):
        """Fixture to return an RDF or HX2 allocation."""
        return rdf_or_hx2_allocation

    @pytest.fixture
    def allocation_user(self, rdf_or_hx2_allocation_user):
        """Fixture to return an RDF or HX2 allocation user."""
        return rdf_or_hx2_allocation_user

    @pytest.fixture
    def allocation_user_inactive_status(self, db):
        """Fixture to create an Inactive AllocationUserStatusChoice."""
        return AllocationUserStatusChoice.objects.create(name="Inactive")

    @pytest.fixture
    def ldap_groupname(self, allocation):
        """Fixture to return the LDAP group name for the allocation."""
        return allocation.ldap_shortname

    def test_sync_ldap_group_membership_remove(
        self,
        ldap_remove_member_mock,
        ldap_add_member_mock,
        user,
        allocation,
        allocation_user_inactive_status,
        ldap_groupname,
    ):
        """Test sync_ldap_group_membership signal."""
        # clear mock calls from setup
        ldap_add_member_mock.reset_mock()
        ldap_remove_member_mock.assert_not_called()

        AllocationUser.objects.create(
            allocation=allocation,
            user=user,
            status=allocation_user_inactive_status,
        )

        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_any_call(
            ldap_groupname, user.username, allow_missing=True
        )

    def test_sync_ldap_group_membership_add(
        self,
        ldap_remove_member_mock,
        ldap_add_member_mock,
        user,
        allocation,
        allocation_user_active_status,
        ldap_groupname,
    ):
        """Test sync_ldap_group_membership signal."""
        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_not_called()

        AllocationUser.objects.create(
            allocation=allocation,
            user=user,
            status=allocation_user_active_status,
        )

        ldap_add_member_mock.assert_any_call(
            ldap_groupname,
            user.username,
            allow_already_present=True,
        )
        ldap_remove_member_mock.assert_not_called()

    def test_ldap_disabled(
        self,
        ldap_remove_member_mock,
        ldap_add_member_mock,
        allocation_user,
        settings,
        allocation_user_inactive_status,
    ):
        """Test that no LDAP operations are performed when LDAP is disabled."""
        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_not_called()
        settings.LDAP_ENABLED = False

        allocation_user.status = allocation_user_inactive_status
        allocation_user.save()

        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_not_called()

    def test_non_rdf_or_hx2_allocation(
        self,
        ldap_remove_member_mock,
        ldap_add_member_mock,
        user,
        project,
        allocation_active_status,
        allocation_user_active_status,
    ):
        """Test that signal does not apply to non-RDF allocations."""
        allocation = Allocation.objects.create(
            project=project, status=allocation_active_status
        )

        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_not_called()

        AllocationUser.objects.create(
            allocation=allocation,
            user=user,
            status=allocation_user_active_status,
        )

        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_not_called()

    def test_inactive_allocation(
        self,
        ldap_remove_member_mock,
        ldap_add_member_mock,
        user,
        allocation,
        allocation_inactive_status,
        allocation_user_active_status,
        remove_ldap_group_members_mock,
    ):
        """Test that no LDAP operations are performed for inactive allocations."""
        allocation.status = allocation_inactive_status
        allocation.save()

        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_not_called()

        AllocationUser.objects.create(
            allocation=allocation,
            user=user,
            status=allocation_user_active_status,
        )

        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_not_called()


class TestAllocationUserSyncHX2AccessGroup(TestAllocationUserSyncLDAPGroupMembership):
    """Tests for allocation_user_sync_hx2_access_group signal handler.

    Inherits from TestAllocationUserSyncLDAPGroupMembership to reuse tests, but
    overrides allocation and ldap_groupname fixtures to use HX2 only values.
    """

    @pytest.fixture
    def allocation(self, hx2_allocation):
        """Fixture to return an HX2 allocation."""
        return hx2_allocation

    @pytest.fixture
    def allocation_user(self, hx2_allocation_user):
        """Fixture to return an HX2 allocation user."""
        return hx2_allocation_user

    @pytest.fixture
    def ldap_groupname(self, settings):
        """Fixture to return the LDAP group name for HX2 access."""
        return settings.LDAP_HX2_ACCESS_GROUP_NAME

    def test_rdf_allocation_does_not_sync(
        self,
        ldap_add_member_mock,
        user,
        rdf_allocation,
        allocation_user_active_status,
        settings,
    ):
        """Test that RDF allocations do not sync HX2 access groups."""
        AllocationUser.objects.create(
            allocation=rdf_allocation,
            user=user,
            status=allocation_user_active_status,
        )
        assert (
            call(
                settings.LDAP_HX2_ACCESS_GROUP_NAME,
                user.username,
                allow_already_present=True,
            )
            not in ldap_add_member_mock.call_args_list
        )


class TestAllocationUserLDAPGroupRemoveMembership:
    """Tests for allocation_user_ldap_group_membership_deletion signal handler."""

    @pytest.fixture
    def allocation(self, rdf_or_hx2_allocation):
        """Fixture to return an RDF or HX2 allocation."""
        return rdf_or_hx2_allocation

    @pytest.fixture
    def allocation_user(self, rdf_or_hx2_allocation_user):
        """Fixture to return an RDF or HX2 allocation user."""
        return rdf_or_hx2_allocation_user

    @pytest.fixture
    def ldap_groupname(self, allocation):
        """Fixture to return the LDAP group name for the allocation."""
        return allocation.ldap_shortname

    def test_success(
        self,
        ldap_remove_member_mock,
        allocation_user,
        user,
        settings,
    ):
        """Test remove_ldap_group_membership signal."""
        ldap_remove_member_mock.assert_not_called()

        allocation_user.delete()

        ldap_remove_member_mock.assert_any_call(
            allocation_user.allocation.ldap_shortname, user.username, allow_missing=True
        )

    def test_ldap_disabled(
        self,
        ldap_remove_member_mock,
        allocation_user,
        settings,
    ):
        """Test that no LDAP operations are performed when LDAP is disabled."""
        ldap_remove_member_mock.assert_not_called()
        settings.LDAP_ENABLED = False

        allocation_user.delete()

        ldap_remove_member_mock.assert_not_called()

    def test_non_rdf_or_hx2_allocation(
        self,
        ldap_remove_member_mock,
        allocation_active_status,
        allocation_user_active_status,
        project,
        user,
    ):
        """Test remove_ldap_group_membership_signal for non-rdf allocation."""
        allocation = Allocation.objects.create(
            project=project,
            status=allocation_active_status,
        )
        allocation_user = AllocationUser.objects.create(
            allocation=allocation,
            user=user,
            status=allocation_user_active_status,
        )

        allocation_user.delete()
        ldap_remove_member_mock.assert_not_called()

    def test_inactive_allocation(
        self,
        remove_ldap_group_members_mock,
        ldap_remove_member_mock,
        allocation_user,
        allocation_inactive_status,
    ):
        """Test that no LDAP operations are performed for inactive allocations."""
        allocation_user.allocation.status = allocation_inactive_status
        allocation_user.allocation.save()

        allocation_user.delete()

        ldap_remove_member_mock.assert_not_called()


class TestAllocationUserHX2AccessGroupDeletion(
    TestAllocationUserLDAPGroupRemoveMembership
):
    """Tests for allocation_user_hx2_access_group_deletion signal handler.

    Inherits from TestAllocationUserLDAPGroupRemoveMembership to reuse tests, but
    overrides allocation and ldap_groupname fixtures to use HX2 only values.
    """

    @pytest.fixture
    def allocation(self, hx2_allocation):
        """Fixture to return an HX2 allocation."""
        return hx2_allocation

    @pytest.fixture
    def allocation_user(self, hx2_allocation_user):
        """Fixture to return an HX2 allocation user."""
        return hx2_allocation_user

    @pytest.fixture
    def ldap_groupname(self, settings):
        """Fixture to return the LDAP group name for HX2 access."""
        return settings.LDAP_HX2_ACCESS_GROUP_NAME

    def test_rdf_allocation_does_not_sync(
        self,
        ldap_remove_member_mock,
        rdf_allocation_user,
        user,
        settings,
    ):
        """Test that RDF allocations do not sync HX2 access groups."""
        rdf_allocation_user.delete()
        assert (
            call(
                settings.LDAP_HX2_ACCESS_GROUP_NAME,
                user.username,
                allow_missing=True,
            )
            not in ldap_remove_member_mock.call_args_list
        )


class _TestInactiveAllocationBase:
    """Base class for testing signals triggered by inactive allocations.

    The leading underscore in the name prevents pytest from collecting this class.
    """

    def test_success(
        self,
        remove_ldap_group_members_mock,
        allocation_inactive_status,
        allocation_user,
    ):
        """Test remove_ldap_group_members_if_allocation_inactive signal."""
        remove_ldap_group_members_mock.assert_not_called()

        # Change allocation status to inactive
        allocation = allocation_user.allocation
        allocation.status = allocation_inactive_status
        allocation.save()

        remove_ldap_group_members_mock.assert_any_call(
            [allocation_user.user.username], allocation.ldap_shortname
        )

    def test_status_active(
        self,
        remove_ldap_group_members_mock,
        allocation,
    ):
        """Test that task is not called when allocation is active."""
        remove_ldap_group_members_mock.assert_not_called()

        # Allocation is already active, so saving shouldn't trigger the task
        allocation.save()

        remove_ldap_group_members_mock.assert_not_called()

    def test_non_rdf_or_hx2_allocation(
        self,
        remove_ldap_group_members_mock,
        project,
        user,
        allocation_user_active_status,
        allocation_active_status,
        allocation_inactive_status,
    ):
        """Test that task is not called for non rdf allocations."""
        allocation = Allocation.objects.create(
            project=project,
            status=allocation_active_status,
        )
        AllocationUser.objects.create(
            allocation=allocation,
            user=user,
            status=allocation_user_active_status,
        )
        allocation.status = allocation_inactive_status
        allocation.save()
        remove_ldap_group_members_mock.assert_not_called()

    def test_ldap_disabled(
        self,
        remove_ldap_group_members_mock,
        allocation,
        allocation_inactive_status,
        settings,
    ):
        """Test that task is not called when LDAP is disabled."""
        settings.LDAP_ENABLED = False
        allocation.status = allocation_inactive_status
        allocation.save()

        remove_ldap_group_members_mock.assert_not_called()


class TestAllocationRemoveLDAPGroupMembersIfInactive(_TestInactiveAllocationBase):
    """Tests for allocation_remove_ldap_group_members_if_inactive signal handler."""

    @pytest.fixture
    def allocation(self, rdf_or_hx2_allocation):
        """Fixture to return an RDF or HX2 allocation."""
        return rdf_or_hx2_allocation

    @pytest.fixture
    def allocation_user(self, rdf_or_hx2_allocation_user):
        """Fixture to return an RDF or HX2 allocation user."""
        return rdf_or_hx2_allocation_user

    def test_feature_flag_disabled(
        self,
        remove_ldap_group_members_mock,
        allocation_inactive_status,
        allocation_user,
        settings,
    ):
        """Test that feature flag disables signal only for RDFAllocation's."""
        settings.ENABLE_RDF_ALLOCATION_LIFECYCLE = False
        allocation_user.allocation.status = allocation_inactive_status
        allocation_user.allocation.save()

        call_should_be_made = (
            False if isinstance(allocation_user.allocation, RDFAllocation) else True
        )
        call_made = (
            call(
                [allocation_user.user.username],
                allocation_user.allocation.ldap_shortname,
            )
            in remove_ldap_group_members_mock.call_args_list
        )

        assert call_should_be_made == call_made


class TestAllocationRemoveHX2AccessGroupIfInactive(_TestInactiveAllocationBase):
    """Tests for allocation_remove_hx2_access_group_if_inactive signal handler."""

    @pytest.fixture
    def allocation(self, hx2_allocation):
        """Fixture to return an HX2 allocation."""
        return hx2_allocation

    @pytest.fixture
    def allocation_user(self, hx2_allocation_user):
        """Fixture to return an HX2 allocation user."""
        return hx2_allocation_user

    def test_rdf_allocation_does_not_sync(
        self,
        remove_ldap_group_members_mock,
        rdf_allocation_user,
        user,
        settings,
        allocation_inactive_status,
    ):
        """Test that RDF allocations do not sync HX2 access groups."""
        rdf_allocation_user.allocation.status = allocation_inactive_status
        rdf_allocation_user.allocation.save()
        assert (
            call(
                [user.username],
                settings.LDAP_HX2_ACCESS_GROUP_NAME,
                allow_missing=True,
            )
            not in remove_ldap_group_members_mock.call_args_list
        )


@pytest.fixture
def zero_quota_mock(mocker):
    """Mock zero_allocation_gpfs_quota task."""
    return mocker.patch("imperial_coldfront_plugin.tasks.zero_allocation_gpfs_quota")


class TestAllocationExpiryZeroQuota:
    """Tests for allocation_expiry_zero_quota signal handler."""

    @pytest.fixture
    def expired_status(self, db):
        """Fixture to create an Expired AllocationStatusChoice."""
        return AllocationStatusChoice.objects.create(name="Expired")

    @pytest.fixture
    def removed_status(self, db):
        """Fixture to create a Removed AllocationStatusChoice."""
        return AllocationStatusChoice.objects.create(name="Removed")

    def test_success(self, rdf_allocation, zero_quota_mock, expired_status):
        """Test that changing allocation status to Expired spawns quota zeroing task."""
        rdf_allocation.status = expired_status
        rdf_allocation.save()
        zero_quota_mock.assert_called_once_with(rdf_allocation.pk)

    def test_does_not_trigger_for_other_statuses(
        self, rdf_allocation, rdf_allocation_gid, zero_quota_mock, removed_status
    ):
        """Test that changing to a non-Expired status does not trigger the task."""
        rdf_allocation.status = removed_status
        rdf_allocation.save()
        zero_quota_mock.assert_not_called()

    def test_skips_new_allocations(
        self,
        project,
        zero_quota_mock,
        expired_status,
    ):
        """Test that creating new allocation does not trigger the task (pk is None)."""
        Allocation.objects.create(project=project, status=expired_status)
        zero_quota_mock.assert_not_called()

    def test_non_rdf_allocation(
        self, project, zero_quota_mock, allocation_active_status, expired_status
    ):
        """Test that expiring a non-rdf allocation does not trigger the task."""
        allocation = Allocation.objects.create(
            project=project, status=allocation_active_status
        )
        allocation.status = expired_status
        allocation.save()
        zero_quota_mock.assert_not_called()

    def test_hx2_allocation_does_not_trigger(
        self,
        hx2_allocation,
        zero_quota_mock,
        expired_status,
    ):
        """Test that expiring an HX2 allocation does not trigger the task."""
        hx2_allocation.status = expired_status
        hx2_allocation.save()
        zero_quota_mock.assert_not_called()

    def test_only_trigger_on_status_change_from_active_to_expired(
        self, rdf_allocation, zero_quota_mock, expired_status, removed_status
    ):
        """Test only triggered when changing from Active to Expired statuses."""
        # changing to removed status doesn't trigger the task
        rdf_allocation.status = removed_status
        rdf_allocation.save()
        zero_quota_mock.assert_not_called()

        # changing from removed to expired doesn't trigger the task either
        zero_quota_mock.reset_mock()
        rdf_allocation.status = expired_status
        rdf_allocation.save()
        zero_quota_mock.assert_not_called()


class TestPreventMultipleHX2AllocationsPerProject:
    """Tests for prevent_multiple_hx2_allocations_per_project signal handler."""

    def test_new_allocation_passes(self, project, rdf_allocation_dependencies):
        """Test that creating a first HX2 allocation for a project passes."""
        hx2_resource = Resource.objects.get(name="HX2")
        allocation_active_status = AllocationStatusChoice.objects.get(name="Active")
        allocation = HX2Allocation.objects.create(
            project=project, status=allocation_active_status
        )
        allocation.resources.add(hx2_resource)

        assert allocation.pk is not None
        assert allocation.resources.filter(pk=hx2_resource.pk).exists()
    def test_duplicate_allocation_raises(
        self, hx2_allocation, rdf_allocation_dependencies
    ):
        """Test that creating a second HX2 allocation for the same project raises."""
        allocation_active_status = AllocationStatusChoice.objects.get(name="Active")

        # Since the hx2_allocation fixture creates an HX2 allocation for the project,
        # trying to create another one should raise a ValueError.
        with pytest.raises(ValueError, match="already has an HX2 allocation"):
            HX2Allocation.objects.create(
                project=hx2_allocation.project,
                status=allocation_active_status,
            )
