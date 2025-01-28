"""Tests for the views of the plugin."""

from http import HTTPStatus
from random import randint

import pytest
from django.conf import settings
from django.core.signing import TimestampSigner
from django.shortcuts import reverse
from pytest_django.asserts import assertRedirects, assertTemplateUsed

from imperial_coldfront_plugin.forms import (
    TermsAndConditionsForm,
    UserSearchForm,
)
from imperial_coldfront_plugin.models import GroupMembership, UnixUID


@pytest.fixture
def timestamp_signer_mock(mocker):
    """Mock the TimestampSigner class.

    Mocking this class allows checking the output token is used where expected.
    """
    mock = mocker.patch("imperial_coldfront_plugin.views.TimestampSigner")
    mock().sign_object.return_value = "dummytoken"
    return mock


class LoginRequiredMixin:
    """Mixin for tests that require a user to be logged in."""

    def test_login_required(self, client):
        """Test for redirect to the login page if the user is not logged in."""
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.FOUND
        assert response.url.startswith(settings.LOGIN_URL)


class TestGroupMembersView(LoginRequiredMixin):
    """Tests for the group members view."""

    def _get_url(self, user_pk=1):
        return reverse("imperial_coldfront_plugin:group_members", args=[user_pk])

    def test_not_group_owner_or_manager(
        self, auth_client_factory, research_group_factory, user_factory
    ):
        """Test that a user who is not the group owner cannot access the view."""
        owner = user_factory(is_pi=True)
        research_group_factory(owner=owner)
        not_owner = user_factory(is_pi=True)

        response = auth_client_factory(not_owner).get(self._get_url(owner.pk))
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.content == b"Permission denied"

    def test_superuser(self, auth_client_factory, research_group_factory, user_factory):
        """Test that a superuser can access the view for any group."""
        owner = user_factory(is_pi=True)
        group, memberships = research_group_factory(owner=owner)
        superuser = user_factory(is_superuser=True)

        response = auth_client_factory(superuser).get(self._get_url(owner.pk))
        assert response.status_code == HTTPStatus.OK
        assert set(response.context["group_members"]) == set(memberships)

    def test_not_pi(self, user_client):
        """Test that a user who is not a PI cannot access the view."""
        response = user_client.get(self._get_url(1))
        assert response.status_code == HTTPStatus.OK
        assert response.context["message"] == "You do not own a group."

    def test_owner(self, auth_client_factory, research_group_factory):
        """Test that the pi that owns a group can access the view."""
        group, memberships = research_group_factory(number_of_members=3)
        response = auth_client_factory(group.owner).get(self._get_url(group.owner.pk))
        assert response.status_code == HTTPStatus.OK
        assert set(response.context["group_members"]) == set(memberships)


class TestUserSearchView(LoginRequiredMixin):
    """Tests for the user search view."""

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:user_search")

    def test_get(self, get_graph_api_client_mock, user_client):
        """Test that the view renders the form for the group owner."""
        response = user_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert isinstance(response.context["form"], UserSearchForm)

    def test_post(self, get_graph_api_client_mock, user_client):
        """Test search form submission."""
        get_graph_api_client_mock().user_search.return_value = []
        response = user_client.post(self._get_url(), data={"search": "foo"})
        assert response.status_code == HTTPStatus.OK
        assert response.context["search_results"] == []

    def test_search_filter(
        self, get_graph_api_client_mock, user_client, parsed_profile
    ):
        """Test that the search results are filtered correctly."""
        invalid_profile = parsed_profile.copy()
        invalid_profile["record_status"] = "Dead"

        get_graph_api_client_mock().user_search.return_value = [
            parsed_profile,
            invalid_profile,
        ]
        response = user_client.post(self._get_url(), data={"search": "foo"})
        assert response.status_code == HTTPStatus.OK
        assert response.context["search_results"] == [parsed_profile]


@pytest.fixture
def get_graph_api_client_mock(mocker, parsed_profile):
    """Mock out imperial_coldfront_plugin.views.get_graph_api_client."""
    mock = mocker.patch("imperial_coldfront_plugin.views.get_graph_api_client")
    mock().user_profile.return_value = parsed_profile
    return mock


class TestSendGroupInviteView(LoginRequiredMixin):
    """Tests for the send group invite view."""

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:send_group_invite")

    def test_not_group_owner(self, user_client):
        """Test that the view sends an email when a POST request is made."""
        response = user_client.post(self._get_url())
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.content == b"You are not a group owner."

    def test_manager_can_access(
        self, manager_in_group, auth_client_factory, get_graph_api_client_mock
    ):
        """Test that a group manager can access the view."""
        manager, group = manager_in_group
        client = auth_client_factory(manager)
        response = client.post(self._get_url(), data={"username": "username"})
        assert response.status_code == 200

    def test_post_valid(
        self,
        get_graph_api_client_mock,
        parsed_profile,
        pi,
        pi_group,
        pi_client,
        mailoutbox,
        timestamp_signer_mock,
    ):
        """Test that the view sends an email when a POST request is made."""
        username = "username"
        invitee_email = parsed_profile["email"]
        response = pi_client.post(self._get_url(), data={"username": username})
        assert response.status_code == HTTPStatus.OK
        assert f"Invitation sent to {invitee_email}" in response.content.decode()

        email = mailoutbox[0]
        assert email.subject == "HPC Access Invitation"
        assert email.to == [invitee_email]
        token = timestamp_signer_mock().sign_object.return_value
        assert (
            "http://testserver"
            + reverse("imperial_coldfront_plugin:accept_group_invite", args=[token])
            in email.body
        )

    def test_post_ineligible_user(
        self, get_graph_api_client_mock, pi, pi_group, pi_client, mocker
    ):
        """Check that specified user is checked for eligibility."""
        user_filter_mock = mocker.patch(
            "imperial_coldfront_plugin.views.user_eligible_for_hpc_access"
        )
        user_filter_mock.return_value = False
        response = pi_client.post(self._get_url(), data={"username": "username"})
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content == b"User not found or not eligible"

    @pytest.mark.parametrize(
        "email,error",
        [
            ("", "This field is required."),
            ("notanemail", "Enter a valid email address."),
        ],
    )
    def test_post_invalid(self, pi_client, pi_group, mailoutbox, email, error):
        """Test the view renders the form with errors when invalid data is posted."""
        response = pi_client.post(self._get_url())
        response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content == b"Invalid data"
        assert len(mailoutbox) == 0


class TestAcceptGroupInvite(LoginRequiredMixin):
    """Tests for the accept group invite view."""

    def _get_url(self, token="dummy_token"):
        return reverse("imperial_coldfront_plugin:accept_group_invite", args=[token])

    def _get_token(self, invitee_email, inviter_pk):
        ts = TimestampSigner()
        return ts.sign_object(
            {"invitee_email": invitee_email, "inviter_pk": inviter_pk}
        )

    def test_get_invalid_token(self, user_client):
        """Test that the view renders the form for the group owner."""
        response = user_client.get(self._get_url())
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content == b"Bad token"

    def test_get_expired_token(self, settings, user_client):
        """Test that the view rejects expired tokens."""
        settings.INVITATION_TOKEN_TIMEOUT = 0  # make token expire immediately
        token = self._get_token("", 1)
        response = user_client.get(self._get_url(token))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content == b"Expired token"

    def test_get_wrong_email(self, user_client):
        """Test that the view rejects tokens with the wrong email."""
        token = self._get_token("foo@bar.com", 1)
        response = user_client.get(self._get_url(token))
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert (
            response.content
            == b"The invite token is not associated with this email address."
        )

    def test_get_valid_token(self, user_client, pi_group, user):
        """Test that the view accepts valid tokens."""
        token = self._get_token(user.email, pi_group.owner.pk)
        response = user_client.get(self._get_url(token))
        assert response.status_code == HTTPStatus.OK
        assertTemplateUsed(
            response, "imperial_coldfront_plugin/member_terms_and_conditions.html"
        )
        assert isinstance(response.context["form"], TermsAndConditionsForm)

    def test_post_invalid(self, user_client, pi_group, user):
        """Test that view renders the form with errors when invalid data is posted."""
        token = self._get_token(user.email, pi_group.owner.pk)
        response = user_client.post(self._get_url(token), data={})
        assert response.status_code == HTTPStatus.OK
        assert response.context["form"].errors == {
            "accept": ["You must accept the terms and conditions"]
        }

    def test_post_valid(self, user_client, pi_group, user):
        """Test that the view adds the user to the group when valid data is posted."""
        token = self._get_token(user.email, pi_group.owner.pk)
        response = user_client.post(self._get_url(token), data={"accept": True})
        assert response.status_code == HTTPStatus.OK
        assertTemplateUsed(
            response, "imperial_coldfront_plugin/accept_group_invite.html"
        )

    def test_post_valid_already_member(self, user_client, pi_group, user):
        """Test that the view doesn't duplicate group memberships."""
        token = self._get_token(user.email, pi_group.owner.pk)
        user_client.post(self._get_url(token), data={"accept": True})
        GroupMembership.objects.get(group=pi_group, member=user)


class TestCheckAccessView(LoginRequiredMixin):
    """Tests for the check_access view."""

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:check_access")

    def test_pi(self, pi_client):
        """Test that the view works for PIs."""
        response = pi_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert (
            response.context["message"] == "You have access to RCS resources as a PI."
        )

    def test_superuser(self, auth_client_factory, user_factory):
        """Test that the view works for superusers."""
        superuser = user_factory(is_superuser=True)
        client = auth_client_factory(superuser)
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert (
            response.context["message"]
            == "You have access to RCS resources as an administrator."
        )

    def test_group_member(self, pi, pi_group, auth_client_factory):
        """Test that the view works for members of a group."""
        member = pi_group.groupmembership_set.first().member
        response = auth_client_factory(member).get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert response.context["message"] == (
            "You have been granted access to the RCS compute cluster as a member "
            f"of the research group of {pi.get_full_name()}."
        )

    def test_not_group_member(self, user_client):
        """Test the view response for users who don't have access."""
        response = user_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert (
            response.context["message"]
            == "You do not currently have access to the RCS compute cluster."
        )


class TestRemoveGroupMemberView(LoginRequiredMixin):
    """Tests for the remove group member view."""

    def _get_url(self, group_membership_pk=1):
        return reverse(
            "imperial_coldfront_plugin:remove_group_member", args=[group_membership_pk]
        )

    def test_not_group_owner_or_manager(
        self, research_group_factory, auth_client_factory, user_client, pi_group
    ):
        """Test non group owner or manager cannot access the view."""
        group, memberships = research_group_factory(number_of_members=1)
        client = auth_client_factory(group.owner)
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.content == b"Permission denied"

        group_membership = pi_group.groupmembership_set.first()
        response = user_client.get(self._get_url(group_membership.pk))
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.content == b"Permission denied"

    def test_group_owner(self, pi_client, pi_group):
        """Test that the group owner can remove a group member."""
        group_membership = pi_group.groupmembership_set.first()
        response = pi_client.get(self._get_url(group_membership.pk))
        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:group_members",
                args=[group_membership.group.owner.pk],
            ),
        )

    def test_invalid_groupmembership(self, user_client):
        """Test the view response for an invalid group membership."""
        response = user_client.get(self._get_url(1))
        assert response.status_code == HTTPStatus.NOT_FOUND

    @pytest.mark.xfail
    def test_manager_can_access(self, manager_in_group, auth_client_factory):
        """Test that a group manager can access the view."""
        manager, group = manager_in_group
        client = auth_client_factory(manager)
        response = client.get(self._get_url())
        assert response.status_code == 200


class TestGetActiveUsersView:
    """Tests for the get active users view."""

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:get_active_users")

    def test_user(self, auth_client_factory, research_group_factory):
        """Test the get_active_users view returns the right data."""
        group, memberships = research_group_factory(number_of_members=1)
        user = memberships[0].member
        user_uid = UnixUID.objects.create(user=user, identifier=randint(0, 100000))
        UnixUID.objects.create(user=group.owner, identifier=randint(0, 100000))

        response = auth_client_factory(user).get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        expected = bytes(
            f"{user.username}:x:{user_uid.identifier}:{group.gid}:"
            f"{user.first_name} {user.last_name}:"
            f"/rds/general/user/{user.username}/home:/bin/bash",
            "utf-8",
        )
        psswd_list = response.content.split(b"\n")
        assert len(psswd_list) == 3
        assert psswd_list[0] == expected

    def test_owner(self, auth_client_factory, research_group_factory):
        """Test the get_active_users view returns the right data."""
        group, memberships = research_group_factory(number_of_members=0)
        owner_uid = UnixUID.objects.create(
            user=group.owner, identifier=randint(0, 100000)
        )

        response = auth_client_factory(group.owner).get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        expected = bytes(
            f"{group.owner.username}:x:{owner_uid.identifier}:{group.gid}:"
            f"{group.owner.first_name} {group.owner.last_name}:"
            f"/rds/general/user/{group.owner.username}/home:/bin/bash",
            "utf-8",
        )
        psswd_list = response.content.split(b"\n")
        assert len(psswd_list) == 2
        assert psswd_list[0] == expected

    def test_no_unixuid(self, auth_client_factory, research_group_factory):
        """Test the get_active_users view returns the right data."""
        group, memberships = research_group_factory(number_of_members=1)

        response = auth_client_factory(group.owner).get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert b"" == response.content


class TestMakeGroupManagerView(LoginRequiredMixin):
    """Tests for the make group manager view."""

    def _get_url(self, group_membership_pk=1):
        return reverse(
            "imperial_coldfront_plugin:make_manager", args=[group_membership_pk]
        )

    def test_not_group_owner(
        self, research_group_factory, auth_client_factory, user_client, pi_group
    ):
        """Test non group owner or manager cannot access the view."""
        group, memberships = research_group_factory(number_of_members=1)
        client = auth_client_factory(group.owner)
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.content == b"Permission denied"

    def test_group_owner(self, pi_client, pi_group):
        """Test that the group owner can make a group member a manager."""
        group_membership = pi_group.groupmembership_set.first()
        response = pi_client.get(self._get_url(group_membership.pk))
        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:group_members",
                args=[group_membership.group.owner.pk],
            ),
        )

    def test_invalid_groupmembership(self, user_client):
        """Test the view response for an invalid group membership."""
        response = user_client.get(self._get_url(1))
        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_successful_manager_promotion(self, pi_client, pi_group, mailoutbox):
        """Test successful promotion of group member to manager."""
        group_membership = pi_group.groupmembership_set.first()

        response = pi_client.get(self._get_url(group_membership.pk))

        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:group_members",
                args=[group_membership.group.owner.pk],
            ),
        )

        group_membership.refresh_from_db()
        assert group_membership.is_manager is True

        assert len(mailoutbox) == 2
        owner_email = mailoutbox[0]
        member_email = mailoutbox[1]

        assert owner_email.subject == "New group manager"
        assert owner_email.to == [pi_group.owner.email]
        assert (
            f"{group_membership.member.get_full_name()} has been made a manager of your group."  # noqa: E501
            in owner_email.body
        )

        assert member_email.subject == f"HPC {pi_group.name} group update"
        assert member_email.to == [group_membership.member.email]
        assert (
            f"You have been made a manager of the group {pi_group.name}."
            in member_email.body
        )


class TestRemoveGroupManagerView(LoginRequiredMixin):
    """Tests for the remove group manager view."""

    def _get_url(self, group_membership_pk=1):
        return reverse(
            "imperial_coldfront_plugin:remove_manager", args=[group_membership_pk]
        )

    def test_not_group_owner(
        self, research_group_factory, auth_client_factory, user_client, pi_group
    ):
        """Test non group owner or manager cannot access the view."""
        group, memberships = research_group_factory(number_of_members=1)
        client = auth_client_factory(group.owner)
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.content == b"Permission denied"

    def test_group_owner(self, pi_client, pi_group):
        """Test that the group owner can remove a group manager."""
        group_membership = pi_group.groupmembership_set.first()
        response = pi_client.get(self._get_url(group_membership.pk))
        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:group_members",
                args=[group_membership.group.owner.pk],
            ),
        )

    def test_invalid_groupmembership(self, user_client):
        """Test the view response for an invalid group membership."""
        response = user_client.get(self._get_url(1))
        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_successful_manager_removal(self, pi_client, pi_group, mailoutbox):
        """Test successful removal of group manager."""
        group_membership = pi_group.groupmembership_set.first()
        group_membership.is_manager = True
        group_membership.save()

        response = pi_client.get(self._get_url(group_membership.pk))

        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:group_members",
                args=[group_membership.group.owner.pk],
            ),
        )

        group_membership.refresh_from_db()
        assert group_membership.is_manager is False

        assert len(mailoutbox) == 2
        owner_email = mailoutbox[0]
        member_email = mailoutbox[1]

        assert owner_email.subject == "Group manager removed"
        assert owner_email.to == [pi_group.owner.email]
        assert (
            f"{group_membership.member.get_full_name()} has been removed as manager of your group."  # noqa: E501
            in owner_email.body
        )

        assert member_email.subject == f"HPC {pi_group.name} group update"
        assert member_email.to == [group_membership.member.email]
        assert (
            f"You have been removed as a manager of the group {pi_group.name}."
            in member_email.body
        )
