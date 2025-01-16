"""Tests for the views of the plugin."""

from http import HTTPStatus

import pytest
from django.conf import settings
from django.core.signing import TimestampSigner
from django.shortcuts import reverse

from imperial_coldfront_plugin.forms import GroupMembershipForm
from imperial_coldfront_plugin.models import GroupMembership


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


class TestSendGroupInviteView(LoginRequiredMixin):
    """Tests for the send group invite view."""

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:send_group_invite")

    def test_not_group_owner(self, user_client):
        """Test that the view sends an email when a POST request is made."""
        response = user_client.get(self._get_url())
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.content == b"You are not a group owner."

    def test_get(self, pi_group, pi_client):
        """Test that the view renders the form for the group owner."""
        response = pi_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert isinstance(response.context["form"], GroupMembershipForm)

    def test_post_valid(
        self, pi, pi_group, pi_client, mailoutbox, timestamp_signer_mock
    ):
        """Test that the view sends an email when a POST request is made."""
        invitee_email = "foo@bar.com"
        response = pi_client.post(
            self._get_url(), data={"invitee_email": invitee_email}
        )
        assert response.status_code == HTTPStatus.OK
        assert f"Invitation sent to {invitee_email}" in response.content.decode()

        email = mailoutbox[0]
        assert email.subject == "You've been invited to a group"
        assert email.to == [invitee_email]
        token = timestamp_signer_mock().sign_object.return_value
        assert (
            "http://testserver"
            + reverse("imperial_coldfront_plugin:accept_group_invite", args=[token])
            in email.body
        )

    def test_manager_can_access(
        self, auth_client_factory, user_factory, research_group_factory
    ):
        """Test that a user with is_manager=True can access the view."""
        manager = user_factory()
        owner = user_factory(is_pi=True)
        group, _ = research_group_factory(owner=owner)

        GroupMembership.objects.create(group=group, member=manager, is_manager=True)

        # Authenticate as the manager and try to access the invite view.
        client = auth_client_factory(manager)
        response = client.get(self._get_url())
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "email,error",
        [
            ("", "This field is required."),
            ("notanemail", "Enter a valid email address."),
        ],
    )
    def test_post_invalid(self, pi_client, pi_group, mailoutbox, email, error):
        """Test the view renders the form with errors when invalid data is posted."""
        response = pi_client.post(self._get_url(), data={"invitee_email": email})
        response.status_code == HTTPStatus.OK
        assert response.context["form"].errors == {"invitee_email": [error]}
        assert error in response.content.decode()
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
        assert b"You have accepted a group invitation" in response.content
        GroupMembership.objects.get(group=pi_group, member=user)

    def test_get_valid_token_already_member(self, user_client, pi_group, user):
        """Test that the view doesn't duplicate group memberships."""
        token = self._get_token(user.email, pi_group.owner.pk)
        user_client.get(self._get_url(token))
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
