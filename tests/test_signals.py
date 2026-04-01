import pytest
from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
    AllocationStatusChoice,
    AllocationUser,
    AllocationUserStatusChoice,
)


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
        "imperial_coldfront_plugin.signals.remove_allocation_group_members"
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
    def allocation_user_inactive_status(self, db):
        """Fixture to create an Inactive AllocationUserStatusChoice."""
        return AllocationUserStatusChoice.objects.create(name="Inactive")

    def test_sync_ldap_group_membership_remove(
        self,
        ldap_remove_member_mock,
        ldap_add_member_mock,
        user,
        rdf_allocation_ldap_name,
        rdf_allocation,
        allocation_user_inactive_status,
    ):
        """Test sync_ldap_group_membership signal."""
        # clear mock calls from setup
        ldap_add_member_mock.reset_mock()
        ldap_remove_member_mock.assert_not_called()

        AllocationUser.objects.create(
            allocation=rdf_allocation, user=user, status=allocation_user_inactive_status
        )

        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_called_once_with(
            rdf_allocation_ldap_name, user.username, allow_missing=True
        )

    def test_sync_ldap_group_membership_add(
        self,
        ldap_remove_member_mock,
        ldap_add_member_mock,
        user,
        rdf_allocation_ldap_name,
        rdf_allocation,
        allocation_user_active_status,
    ):
        """Test sync_ldap_group_membership signal."""
        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_not_called()

        AllocationUser.objects.create(
            allocation=rdf_allocation, user=user, status=allocation_user_active_status
        )

        ldap_add_member_mock.assert_called_once_with(
            rdf_allocation_ldap_name, user.username, allow_already_present=True
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

    def test_non_rdf_allocation(
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
        rdf_allocation,
        allocation_inactive_status,
        allocation_user_active_status,
    ):
        """Test that no LDAP operations are performed for inactive allocations."""
        rdf_allocation.status = allocation_inactive_status
        rdf_allocation.save()

        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_not_called()

        AllocationUser.objects.create(
            allocation=rdf_allocation,
            user=user,
            status=allocation_user_active_status,
        )

        ldap_add_member_mock.assert_not_called()
        ldap_remove_member_mock.assert_not_called()


class TestAllocationUserLDAPGroupRemoveMembership:
    """Tests for allocation_user_ldap_group_membership_deletion signal handler."""

    def test_success(
        self,
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

    def test_non_rdf_allocation(
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
        remove_allocation_group_members_mock,
        ldap_remove_member_mock,
        allocation_user,
        allocation_inactive_status,
    ):
        """Test that no LDAP operations are performed for inactive allocations."""
        allocation_user.allocation.status = allocation_inactive_status
        allocation_user.allocation.save()

        allocation_user.delete()

        ldap_remove_member_mock.assert_not_called()


class TestAllocationRemoveLDAPGroupMembersIfInactive:
    """Tests for allocation_remove_ldap_group_members_if_inactive signal handler."""

    def test_success(
        self,
        remove_allocation_group_members_mock,
        rdf_allocation,
        allocation_inactive_status,
        allocation_user,
    ):
        """Test remove_ldap_group_members_if_allocation_inactive signal."""
        remove_allocation_group_members_mock.assert_not_called()

        # Change allocation status to inactive
        rdf_allocation.status = allocation_inactive_status
        rdf_allocation.save()

        remove_allocation_group_members_mock.assert_called_once_with(rdf_allocation.pk)

    def test_status_active(
        self,
        remove_allocation_group_members_mock,
        rdf_allocation,
        allocation_user,
    ):
        """Test that task is not called when allocation is active."""
        remove_allocation_group_members_mock.assert_not_called()

        # Allocation is already active, so saving shouldn't trigger the task
        rdf_allocation.save()

        remove_allocation_group_members_mock.assert_not_called()

    def test_non_rdf_allocation(
        self,
        remove_allocation_group_members_mock,
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
        remove_allocation_group_members_mock.assert_not_called()

    def test_ldap_disabled(
        self,
        remove_allocation_group_members_mock,
        rdf_allocation,
        allocation_inactive_status,
        settings,
    ):
        """Test that task is not called when LDAP is disabled."""
        settings.LDAP_ENABLED = False
        rdf_allocation.status = allocation_inactive_status
        rdf_allocation.save()

        remove_allocation_group_members_mock.assert_not_called()


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
