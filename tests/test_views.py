"""Tests for the views of the plugin."""

from http import HTTPStatus

import pytest
from django.conf import settings
from django.shortcuts import reverse


class TestGroupMembersView:
    """Tests for the group members view."""

    def _get_url(self, user_pk):
        return reverse("group_members", args=[user_pk])

    def test_login_required(self, client):
        """Test that the view requires login."""
        response = client.get(self._get_url(1))
        assert response.status_code == HTTPStatus.FOUND
        assert response.url.startswith(settings.LOGIN_URL)

    def test_not_group_owner(
        self, auth_client_factory, research_group_factory, user_factory
    ):
        """Test that a user who is not the group owner cannot access the view."""
        owner = user_factory(is_pi=True)
        research_group_factory(owner=owner)
        not_owner = user_factory(is_pi=True)

        response = auth_client_factory(not_owner).get(self._get_url(owner.pk))
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.content == b"Permission denied"

    @pytest.mark.xfail(reason="This test is expected to fail due to a bug in the code.")
    def test_superuser(self, auth_client_factory, research_group_factory, user_factory):
        """Test that a superuser can access the view for any group."""
        owner = user_factory(is_pi=True)
        group, memberships = research_group_factory(owner=owner)
        superuser = user_factory(is_superuser=True)

        response = auth_client_factory(superuser).get(self._get_url(owner.pk))
        assert response.status_code == HTTPStatus.OK
        assert set(response.context["group_members"]) == set(memberships)

    def test_not_pi(self, auth_client):
        """Test that a user who is not a PI cannot access the view."""
        response = auth_client.get(self._get_url(1))
        assert response.status_code == HTTPStatus.OK
        assert response.context["message"] == "You do not own a group."

    @pytest.mark.xfail(reason="This test is expected to fail due to a bug in the code.")
    def test_owner(self, auth_client_factory, research_group_factory):
        """Test that the pi that owns a group can access the view."""
        group, memberships = research_group_factory(number_of_members=3)
        response = auth_client_factory(group.owner).get(self._get_url(group.owner.pk))
        assert response.status_code == HTTPStatus.OK
        assert set(response.context["group_members"]) == set(memberships)
