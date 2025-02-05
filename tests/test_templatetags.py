"""Tests for template tags."""

import pytest

from imperial_coldfront_plugin.templatetags.home_tags import (
    is_a_group_member,
    is_eligible_to_own_a_group,
    owns_a_group,
)


@pytest.fixture
def get_graph_api_client_mock(mocker, parsed_profile):
    """Mock out get_graph_api_client for home_tags.py."""
    mock = mocker.patch(
        "imperial_coldfront_plugin.templatetags.home_tags.get_graph_api_client"
    )
    mock().user_profile.return_value = parsed_profile
    return mock


class TestHomeTags:
    """Tests for the home_tags template tags."""

    def test_owns_a_group_true(self, pi, pi_group):
        """Test true condition of owns_a_group tag."""
        assert owns_a_group(pi)

    def test_owns_a_group_false(self, user):
        """Test false condition of owns_a_group tag."""
        assert not owns_a_group(user)

    def test_is_a_group_member_true(self, pi_group):
        """Test true condition of is_a_group_member tag."""
        user = pi_group.groupmembership_set.first().member
        assert is_a_group_member(user)

    def test_is_a_group_member_false(self, user):
        """Test false condition of is_a_group_member tag."""
        assert not is_a_group_member(user)

    def test_is_eligible_to_own_a_group_true(
        self, get_graph_api_client_mock, pi_user_profile, user
    ):
        """Test true condition of is_eligible_to_own_a_group tag."""
        get_graph_api_client_mock().user_profile.return_value = pi_user_profile
        assert is_eligible_to_own_a_group(user)

    def test_is_eligible_to_own_a_group_false(self, get_graph_api_client_mock, user):
        """Test false condition of is_eligible_to_own_a_group tag."""
        assert not is_eligible_to_own_a_group(user)
