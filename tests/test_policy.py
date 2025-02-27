import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from imperial_coldfront_plugin.policy import (
    PI_ALLOWED_TITLES,
    PI_DISALLOWED_DEPARTMENTS,
    PI_DISALLOWED_TITLE_QUALIFIERS,
    check_group_owner_manager_or_superuser,
    check_group_owner_or_superuser,
    user_already_has_hpc_access,
    user_eligible_for_hpc_access,
    user_eligible_to_be_pi,
)


def test_user_filter(parsed_profile):
    """Test the user filter passes a valid profile."""
    assert user_eligible_for_hpc_access(parsed_profile)


@pytest.mark.parametrize(
    "override_key, override_value",
    [
        ("user_type", ""),
        ("record_status", ""),
        ("email", None),
        ("name", None),
        ("department", None),
    ],
)
def test_user_filter_invalid(override_key, override_value, parsed_profile):
    """Test the user filter catches invalid profiles."""
    parsed_profile[override_key] = override_value
    assert not user_eligible_for_hpc_access(parsed_profile)


@pytest.mark.parametrize("job_title", PI_ALLOWED_TITLES)
def test_user_eligible_to_be_pi(job_title, pi_user_profile):
    """Test the user filter passes a valid profile."""
    assert user_eligible_to_be_pi(pi_user_profile | dict(job_title=job_title))


@pytest.mark.parametrize(
    "override_key, override_value",
    [
        ("record_status", ""),
        ("entity_type", "whatever"),
    ]
    + [("job_title", qualifier) for qualifier in PI_DISALLOWED_TITLE_QUALIFIERS]
    + [("department", department) for department in PI_DISALLOWED_DEPARTMENTS],
)
def test_user_eligible_to_be_pi_invalid(override_key, override_value, pi_user_profile):
    """Test the pi filter catches invalid profiles."""
    assert not user_eligible_to_be_pi(pi_user_profile | {override_key: override_value})


class TestCheckGroupOwnerManagerOrSuperuser:
    """Tests for the check_group_owner_manager_or_superuser function."""

    def test_pass(self, pi_group, pi_manager_or_superuser):
        """Test the check passes for a group owner or manager or a superuser."""
        check_group_owner_manager_or_superuser(pi_group, pi_manager_or_superuser)

    def test_expired_manager(self, pi_group, pi_group_manager):
        """Test the check fails for an expired manager."""
        pi_group_manager.groupmembership.expiration = timezone.datetime.min
        pi_group_manager.groupmembership.save()
        with pytest.raises(PermissionDenied):
            check_group_owner_manager_or_superuser(pi_group, pi_group_manager)

    def test_user(self, pi_group, user_or_member):
        """Test the check fails for other users."""
        with pytest.raises(PermissionDenied):
            check_group_owner_manager_or_superuser(pi_group, user_or_member)


class TestCheckGroupOwnerOrSuperuser:
    """Tests for the check_group_owner_or_superuser function."""

    def test_pass(self, pi_group, pi_or_superuser):
        """Check the group owner or superuser passes the check."""
        check_group_owner_or_superuser(pi_group, pi_or_superuser)

    def test_manager(self, pi_group, user_member_or_manager):
        """Test the check fails for a other users."""
        with pytest.raises(PermissionDenied):
            check_group_owner_or_superuser(pi_group, user_member_or_manager)


def test_user_already_has_hpc_access_no_user(db):
    """Test if non-existent user already has access."""
    assert not user_already_has_hpc_access("username")


def test_user_already_has_hpc_access(user):
    """Test if a user already has access."""
    assert not user_already_has_hpc_access(user.username)


def test_user_already_has_hpc_access_group_membership(pi_group_member):
    """Test if a user with a group membership already has access."""
    assert user_already_has_hpc_access(pi_group_member.username)


def test_user_already_has_hpc_access_group_owner(pi_group):
    """Test if a user with a group ownership already has access."""
    assert user_already_has_hpc_access(pi_group.owner.username)


def test_user_already_has_hpc_access_superuser(superuser):
    """Test if a superuser already has access."""
    assert user_already_has_hpc_access(superuser.username)
