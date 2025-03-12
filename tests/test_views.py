"""Tests for the views of the plugin."""

from datetime import timedelta
from http import HTTPStatus
from random import randint
from unittest.mock import patch

import pytest
from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
    AllocationStatusChoice,
)
from coldfront.core.resource.models import Resource
from django.conf import settings
from django.core.signing import TimestampSigner
from django.shortcuts import render, reverse
from django.template.loader import render_to_string
from django.utils import timezone
from pytest_django.asserts import assertRedirects, assertTemplateUsed

from imperial_coldfront_plugin.forms import (
    RDFAllocationForm,
    TermsAndConditionsForm,
    UserSearchForm,
)
from imperial_coldfront_plugin.models import ResearchGroup, UnixUID
from imperial_coldfront_plugin.views import (
    format_project_number_to_id,
    get_next_rdf_project_id,
)


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


class GroupMembershipPKMixin:
    """Mixin for tests that require a group membership pk."""

    def test_invalid_groupmembership(self, user_client):
        """Test the view response for an invalid group membership."""
        response = user_client.get(self._get_url())
        assert response.status_code == HTTPStatus.NOT_FOUND


class TestGroupMembersView(LoginRequiredMixin):
    """Tests for the group members view."""

    def _get_url(self, group_pk=1):
        return reverse("imperial_coldfront_plugin:group_members", args=[group_pk])

    def test_permission_denied(self, auth_client_factory, user_or_member, pi_group):
        """Test that unauthorised users cannot access the view."""
        response = auth_client_factory(user_or_member).get(self._get_url(pi_group.pk))
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_get(self, auth_client_factory, pi_manager_or_superuser, pi_group):
        """Test the view for authorised users."""
        client = auth_client_factory(pi_manager_or_superuser)
        response = client.get(self._get_url(pi_group.pk))
        assert response.status_code == HTTPStatus.OK
        assert set(response.context["group_members"]) == set(
            pi_group.groupmembership_set.all()
        )
        assert response.context["is_manager"] == (
            pi_manager_or_superuser.username == "manager"
        )


@pytest.mark.usefixtures("get_graph_api_client_mock")
class TestUserSearchView(LoginRequiredMixin):
    """Tests for the user search view."""

    def _get_url(self, group_pk=1):
        return reverse("imperial_coldfront_plugin:user_search", args=[group_pk])

    def test_get(self, user_client):
        """Test view rendering."""
        response = user_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert isinstance(response.context["form"], UserSearchForm)

    def test_post(self, user_client, parsed_profile):
        """Test search form submission."""
        response = user_client.post(self._get_url(), data={"search": "foo"})
        assert response.status_code == HTTPStatus.OK
        assert response.context["search_results"] == [parsed_profile]

    def test_eligibility_filter(self, mocker, parsed_profile, user_client):
        """Test that the user_eligible_for_hpc_access function is used."""
        filter_mock = mocker.patch(
            "imperial_coldfront_plugin.views.user_eligible_for_hpc_access"
        )
        filter_mock.return_value = False
        response = user_client.post(self._get_url(), data={"search": "foo"})
        assert response.status_code == HTTPStatus.OK
        assert response.context["search_results"] == []
        filter_mock.assert_called_once_with(parsed_profile)

    def test_using_existing_access_filter(self, mocker, user_client, parsed_profile):
        """Test that the user_already_in_group function is used."""
        filter_mock = mocker.patch(
            "imperial_coldfront_plugin.views.user_already_has_hpc_access"
        )
        response = user_client.post(self._get_url(), data={"search": "foo"})
        assert response.status_code == HTTPStatus.OK
        assert response.context["search_results"] == []
        filter_mock.assert_called_once_with(parsed_profile["username"])


@pytest.fixture
def get_graph_api_client_mock(mocker, parsed_profile):
    """Mock out imperial_coldfront_plugin.views.get_graph_api_client."""
    mock = mocker.patch("imperial_coldfront_plugin.views.get_graph_api_client")
    mock().user_profile.return_value = parsed_profile
    mock().user_search_by.return_value = [parsed_profile]
    return mock


@pytest.mark.usefixtures("get_graph_api_client_mock")
class TestSendGroupInviteView(LoginRequiredMixin):
    """Tests for the send group invite view."""

    def _get_url(self, group_pk=1):
        return reverse("imperial_coldfront_plugin:send_group_invite", args=[group_pk])

    def test_permission_denied(self, auth_client_factory, user_or_member, pi_group):
        """Test that the view sends an email when a POST request is made."""
        client = auth_client_factory(user_or_member)
        response = client.post(self._get_url(pi_group.pk))
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_post(
        self,
        auth_client_factory,
        pi_manager_or_superuser,
        pi_group,
        parsed_profile,
        mailoutbox,
        timestamp_signer_mock,
    ):
        """Test successful group invitation."""
        client = auth_client_factory(pi_manager_or_superuser)
        data = {"username": "username", "expiration": timezone.datetime.max.date()}
        response = client.post(self._get_url(pi_group.pk), data=data)
        assert response.status_code == HTTPStatus.OK

        invitee_email = parsed_profile["email"]
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

    def _test_filter(self, client, group):
        data = {"username": "username", "expiration": timezone.datetime.max.date()}
        response = client.post(self._get_url(group.pk), data=data)
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content == b"User not found or not eligible"

    def test_existing_access_filter(self, pi_group, pi_client, parsed_profile, mocker):
        """Test that the user_already_has_hpc_access function is used."""
        mock = mocker.patch(
            "imperial_coldfront_plugin.views.user_already_has_hpc_access"
        )
        mock.return_value = True
        self._test_filter(pi_client, pi_group)
        mock.assert_called_once_with(parsed_profile["username"])

    def test_eligibility_filter(self, pi_group, pi_client, parsed_profile, mocker):
        """Test that the user_eligible_for_hpc_access function is used."""
        mock = mocker.patch(
            "imperial_coldfront_plugin.views.user_eligible_for_hpc_access"
        )
        mock.return_value = False
        self._test_filter(pi_client, pi_group)
        mock.assert_called_once_with(parsed_profile)

    def test_group_expiration_in_past(
        self, get_graph_api_client_mock, pi, pi_group, pi_client
    ):
        """Check that a group expiration in the past is rejected."""
        data = {"username": "username", "expiration": timezone.datetime.min.date()}
        response = pi_client.post(self._get_url(pi_group.pk), data=data)
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content == b"Expiration date should be in the future"

    @pytest.mark.parametrize(
        "email,error",
        [
            ("", "This field is required."),
            ("notanemail", "Enter a valid email address."),
        ],
    )
    def test_post_invalid(self, pi_client, pi_group, mailoutbox, email, error):
        """Test the view renders the form with errors when invalid data is posted."""
        response = pi_client.post(self._get_url(pi_group.pk))
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content == b"Invalid data"
        assert len(mailoutbox) == 0

    def test_user_already_in_group(self, pi_client, pi_group, research_group_factory):
        """Test that a user who is already in the group cannot be invited."""
        group, [membership] = research_group_factory(number_of_members=1)
        data = {
            "username": membership.member.username,
            "expiration": timezone.datetime.max.date(),
        }
        response = pi_client.post(self._get_url(pi_group.pk), data=data)
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content == b"User already in a group"


class TestAcceptGroupInvite(LoginRequiredMixin):
    """Tests for the accept group invite view."""

    def _get_url(self, token="dummy_token"):
        return reverse("imperial_coldfront_plugin:accept_group_invite", args=[token])

    def _get_token(self, invitee_email, group_pk):
        ts = TimestampSigner()
        return ts.sign_object(
            {
                "invitee_email": invitee_email,
                "group_pk": group_pk,
                "expiration": timezone.datetime.max.isoformat(),
            }
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
        token = self._get_token(user.email, pi_group.pk)
        response = user_client.get(self._get_url(token))
        assert response.status_code == HTTPStatus.OK
        assertTemplateUsed(
            response, "imperial_coldfront_plugin/member_terms_and_conditions.html"
        )
        assert isinstance(response.context["form"], TermsAndConditionsForm)

    def test_post_invalid(self, user_client, pi_group, user):
        """Test that view renders the form with errors when invalid data is posted."""
        token = self._get_token(user.email, pi_group.pk)
        response = user_client.post(self._get_url(token), data={})
        assert response.status_code == HTTPStatus.OK
        assert response.context["form"].errors == {
            "accept": ["You must accept the terms and conditions"]
        }

    def test_post_valid(self, user_client, pi_group, user, mailoutbox):
        """Test that the view adds the user to the group when valid data is posted."""
        token = self._get_token(user.email, pi_group.pk)

        response = user_client.post(self._get_url(token), data={"accept": True})
        assert response.status_code == HTTPStatus.OK
        assertTemplateUsed(
            response, "imperial_coldfront_plugin/accept_group_invite.html"
        )
        email = mailoutbox[0]
        assert email.subject == "HPC Access Granted"
        assert email.to == [user.email, pi_group.owner.email]
        assert user.get_full_name() in email.body
        assert user.email in email.body
        assert pi_group.owner.get_full_name() in email.body

    def test_post_valid_already_member(
        self, pi_group, pi_group_member, auth_client_factory
    ):
        """Test that the view doesn't duplicate group memberships."""
        client = auth_client_factory(pi_group_member)
        token = self._get_token(pi_group_member.email, pi_group.pk)
        response = client.post(self._get_url(token), data={"accept": True})
        assert response.status_code == HTTPStatus.BAD_REQUEST


class TestCheckAccessView(LoginRequiredMixin):
    """Tests for the check_access view."""

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:check_access")

    def test_pi(self, pi_client, pi_group):
        """Test that the view works for PIs."""
        response = pi_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert (
            response.context["message"]
            == "You have access as the owner of a HPC access group."
        )

    def test_superuser(self, auth_client_factory, user_factory):
        """Test that the view works for superusers."""
        superuser = user_factory(is_superuser=True)
        client = auth_client_factory(superuser)
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert response.context["message"] == "You have access as an administrator."

    def test_group_member(self, pi, pi_group, pi_group_member, auth_client_factory):
        """Test that the view works for members of a group."""
        response = auth_client_factory(pi_group_member).get(self._get_url())
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


class TestRemoveGroupMemberView(LoginRequiredMixin, GroupMembershipPKMixin):
    """Tests for the remove group member view."""

    def _get_url(self, group_membership_pk=1):
        return reverse(
            "imperial_coldfront_plugin:remove_group_member", args=[group_membership_pk]
        )

    def test_permission_denied(
        self,
        auth_client_factory,
        user_or_member,
        pi_group_membership,
    ):
        """Test non group owner or manager cannot access the view."""
        client = auth_client_factory(user_or_member)
        response = client.get(self._get_url(pi_group_membership.pk))
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_get(
        self, auth_client_factory, pi_manager_or_superuser, pi_group, pi_group_member
    ):
        """Test that the group owner can remove a group member."""
        group_membership = pi_group_member.groupmembership
        client = auth_client_factory(pi_manager_or_superuser)
        response = client.get(self._get_url(group_membership.pk))
        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:group_members",
                args=[group_membership.group.pk],
            ),
        )


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


class TestGetGroupDataView:
    """Tests for the get group data view."""

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:get_group_data")

    def test_user(self, client, research_group_factory):
        """Test the get_group_data view returns the right data."""
        group, memberships = research_group_factory(number_of_members=2)
        user1 = memberships[0].member
        user2 = memberships[1].member

        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        expected = bytes(
            f"{group.name}:x:{group.gid}:{user1},{user2}\n",
            "utf-8",
        )
        assert response.content == expected


class TestMakeGroupManagerView(LoginRequiredMixin, GroupMembershipPKMixin):
    """Tests for the make group manager view."""

    def _get_url(self, group_membership_pk=1):
        return reverse(
            "imperial_coldfront_plugin:make_manager", args=[group_membership_pk]
        )

    def test_permission_denied(
        self, auth_client_factory, user_member_or_manager, pi_group_membership
    ):
        """Test non group owner or manager cannot access the view."""
        client = auth_client_factory(user_member_or_manager)
        response = client.get(self._get_url(pi_group_membership.pk))
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_get(
        self,
        auth_client_factory,
        pi_or_superuser,
        pi_group,
        mailoutbox,
        pi_group_member,
        pi_group_membership,
    ):
        """Test successful promotion of group member to manager."""
        client = auth_client_factory(pi_or_superuser)
        response = client.get(self._get_url(pi_group_membership.pk))

        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:group_members",
                args=[pi_group.pk],
            ),
        )

        pi_group_membership.refresh_from_db()
        assert pi_group_membership.is_manager is True

        assert len(mailoutbox) == 1
        email = mailoutbox[0]

        assert email.subject == "HPC Access Manager Added"
        assert email.to == [pi_group_member.email, pi_group.owner.email]
        assert pi_group_member.email in email.body
        assert pi_group_member.get_full_name() in email.body
        assert pi_group.owner.get_full_name() in email.body

    def test_expired_membership(
        self, auth_client_factory, pi_or_superuser, pi_group_membership
    ):
        """Test that an expired group membership cannot be made a manager."""
        pi_group_membership.expiration = timezone.datetime.min.date()
        pi_group_membership.save()

        client = auth_client_factory(pi_or_superuser)
        response = client.get(self._get_url(pi_group_membership.pk))
        assert response.content == b"Membership has expired."
        assert response.status_code == HTTPStatus.BAD_REQUEST


class TestRemoveGroupManagerView(LoginRequiredMixin, GroupMembershipPKMixin):
    """Tests for the remove group manager view."""

    def _get_url(self, group_membership_pk=1):
        return reverse(
            "imperial_coldfront_plugin:remove_manager", args=[group_membership_pk]
        )

    def test_permission_denied(
        self, auth_client_factory, user_member_or_manager, pi_group_manager
    ):
        """Test non group owner or manager cannot access the view."""
        # group, memberships = research_group_factory(number_of_members=1)
        client = auth_client_factory(user_member_or_manager)
        response = client.get(self._get_url(pi_group_manager.groupmembership.pk))
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_successful_manager_removal(
        self,
        auth_client_factory,
        pi_or_superuser,
        pi_group,
        pi_group_manager,
        user_factory,
        mailoutbox,
    ):
        """Test successful removal of group manager."""
        group_membership = pi_group_manager.groupmembership
        client = auth_client_factory(pi_or_superuser)
        response = client.get(self._get_url(group_membership.pk))

        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:group_members",
                args=[group_membership.group.pk],
            ),
        )

        group_membership.refresh_from_db()
        assert group_membership.is_manager is False

        assert len(mailoutbox) == 1
        email = mailoutbox[0]

        assert email.subject == "HPC Access Manager Removed"
        assert email.to == [pi_group_manager.email, pi_group.owner.email]
        assert pi_group_manager.email in email.body
        assert pi_group_manager.get_full_name() in email.body


class TestGroupMembershipExtendView(LoginRequiredMixin, GroupMembershipPKMixin):
    """Tests for the group membership extend view."""

    def _get_url(self, group_membership_pk=1):
        return reverse(
            "imperial_coldfront_plugin:extend_membership", args=[group_membership_pk]
        )

    def test_permission_denied(
        self, auth_client_factory, user_or_member, pi_group_membership
    ):
        """Test non group owner or non group manager cannot access the view."""
        client = auth_client_factory(user_or_member)
        response = client.get(self._get_url(pi_group_membership.pk))
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_manager_cannot_extend_own_membership(
        self, pi_group_manager, auth_client_factory
    ):
        """Test that a group manager cannot extend their own membership."""
        group_membership = pi_group_manager.groupmembership
        client = auth_client_factory(pi_group_manager)
        response = client.get(self._get_url(group_membership.pk))
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.content == b"You cannot extend your own membership."

    def test_successful_membership_extension(
        self, auth_client_factory, pi_manager_or_superuser, pi_group_membership
    ):
        """Test successful extension of group membership."""
        client = auth_client_factory(pi_manager_or_superuser)
        response = client.post(
            self._get_url(pi_group_membership.pk), data={"extend_length": 120}
        )

        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:group_members",
                args=[pi_group_membership.group.pk],
            ),
        )

        current_expiration = pi_group_membership.expiration

        pi_group_membership.refresh_from_db()

        assert pi_group_membership.expiration == current_expiration + timedelta(
            days=120
        )


class TestHomeView:
    """Test rendering of the home view.

    This set of tests does not call the view function for the home page directly as
    that is a Coldfront view. Instead, it checks the rendering logic of the template
    that we override from the plugin.
    """

    @pytest.fixture
    def get_graph_api_client_mock(self, mocker, parsed_profile):
        """Mock out get_graph_api_client for home_tags.py."""
        mock = mocker.patch(
            "imperial_coldfront_plugin.templatetags.home_tags.get_graph_api_client"
        )
        mock().user_profile.return_value = parsed_profile
        return mock

    @pytest.fixture
    def eligible_html(self):
        """The html rendered when a user is eligible to create a HPC access group."""
        return render_to_string("imperial_coldfront_plugin/eligible_pi.html")

    @pytest.fixture
    def request_(self, rf, user):
        """A request object with a user."""
        request = rf.get("/")
        request.user = user
        return request

    def test_get_standard_user(
        self, request_, get_graph_api_client_mock, eligible_html
    ):
        """Test that the home view renders correctly for a standard user."""
        response = render(request_, "imperial_coldfront_plugin/home.html")

        assert response.status_code == 200
        assert eligible_html not in response.content.decode()

    def test_get_pi(
        self, request_, get_graph_api_client_mock, eligible_html, pi_user_profile
    ):
        """Test rendering for a user eligible to create a HPC access group."""
        get_graph_api_client_mock().user_profile.return_value = pi_user_profile

        response = render(request_, "imperial_coldfront_plugin/home.html")

        assert response.status_code == 200
        assert eligible_html in response.content.decode()

    def test_get_pi_group_member(
        self,
        request_,
        pi_group,
        get_graph_api_client_mock,
        eligible_html,
        pi_user_profile,
        pi_group_member,
    ):
        """Test rendering for user ineligible because of another group membership."""
        get_graph_api_client_mock().user_profile.return_value = pi_user_profile
        request_.user = pi_group_member

        response = render(request_, "imperial_coldfront_plugin/home.html")

        assert response.status_code == 200
        assert eligible_html not in response.content.decode()


@pytest.fixture
def eligible_pi_mock(mocker):
    """Mock the user_eligible_to_be_pi function."""
    return mocker.patch("imperial_coldfront_plugin.views.user_eligible_to_be_pi")


@pytest.fixture
def message_mock(mocker):
    """Mock the message system, as it is not available in tests.

    See https://stackoverflow.com/a/27300365/3778792 and other answers.
    """
    return mocker.patch("imperial_coldfront_plugin.views.messages")


@pytest.mark.usefixtures("get_graph_api_client_mock", "message_mock")
class TestCreateGroupView(LoginRequiredMixin):
    """Tests for the research group creation view."""

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:research_group_create")

    def test_not_pi_cannot_create_groups(
        self,
        auth_client_factory,
        user_or_member,
        eligible_pi_mock,
    ):
        """Test a non-pi cannot create groups."""
        client = auth_client_factory(user_or_member)
        eligible_pi_mock.return_value = False
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_potential_pi_in_group_cannot_create_groups(
        self,
        auth_client_factory,
        pi_group_member,
        eligible_pi_mock,
    ):
        """Test a potential pi already in a group cannot create groups."""
        client = auth_client_factory(pi_group_member)
        eligible_pi_mock.return_value = True
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_pi_get_the_terms_and_conditions_form(self, pi_client, eligible_pi_mock):
        """Test a pi is shown the T&C."""
        eligible_pi_mock.return_value = True
        response = pi_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assertTemplateUsed(
            response, "imperial_coldfront_plugin/research_group_terms.html"
        )
        assert isinstance(response.context["form"], TermsAndConditionsForm)

    def test_group_exist_redirect_to_that_one(
        self,
        auth_client_factory,
        pi_group,
        eligible_pi_mock,
    ):
        """Test that if group exists, it redirects to it."""
        pi = pi_group.owner
        client = auth_client_factory(pi)
        eligible_pi_mock.return_value = True
        response = client.post(self._get_url(), data={"accept": True})
        assert response.status_code == HTTPStatus.FOUND
        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:group_members",
                kwargs=dict(group_pk=pi_group.pk),
            ),
        )

    def test_new_group_created(
        self,
        auth_client_factory,
        pi,
        eligible_pi_mock,
    ):
        """Test that a new group is created."""
        with pytest.raises(ResearchGroup.DoesNotExist):
            ResearchGroup.objects.get(owner=pi)
        client = auth_client_factory(pi)
        eligible_pi_mock.return_value = True
        response = client.post(self._get_url(), data={"accept": True})
        group = ResearchGroup.objects.get(owner=pi)
        assert response.status_code == HTTPStatus.FOUND
        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:group_members",
                kwargs=dict(group_pk=group.pk),
            ),
        )


class TestGetNextRdfProjectId:
    """Tests for the get_next_rdf_project_id utility function."""

    def test_next_id(self, pi_project, rdf_allocation_dependencies):
        """Check correct next id is generated from existing id values."""
        rdf_resource = Resource.objects.get(name="RDF Project Storage Space")
        rdf_id_attribute_type = AllocationAttributeType.objects.get(
            name="RDF Project ID"
        )

        allocation_active_status = AllocationStatusChoice.objects.get(name="Active")
        allocation = Allocation.objects.create(
            project=pi_project, status=allocation_active_status
        )
        allocation.resources.add(rdf_resource)

        last_project_number = 23
        AllocationAttribute.objects.create(
            allocation_attribute_type=rdf_id_attribute_type,
            allocation=allocation,
            value=format_project_number_to_id(last_project_number),
        )

        assert get_next_rdf_project_id() == format_project_number_to_id(
            last_project_number + 1
        )

    def test_first(self, db):
        """Check initial id generation."""
        assert get_next_rdf_project_id() == format_project_number_to_id(1)


class TestAddRDFStorageAllocation(LoginRequiredMixin):
    """Tests for the add_rdf_storage_allocation view."""

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:add_rdf_storage_allocation")

    def test_non_admin_forbidden(self, user_member_or_manager, auth_client_factory):
        """Test non-admin users cannot access the page."""
        client = auth_client_factory(user_member_or_manager)
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_get(self, superuser_client):
        """Check form rendering."""
        response = superuser_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert isinstance(response.context["form"], RDFAllocationForm)

    @patch("imperial_coldfront_plugin.views.ldap_create_group_in_background")
    def test_post(
        self,
        ldap_create_group_mock,
        pi_project,
        superuser_client,
        rdf_allocation_dependencies,
    ):
        """Test successful project creation."""
        end_date = timezone.datetime.max.date()
        size = 10
        response = superuser_client.post(
            self._get_url(),
            data=dict(project=pi_project.pk, end_date=end_date, size=size),
        )
        assertRedirects(response, reverse("home"), fetch_redirect_response=False)

        project_id = format_project_number_to_id(1)
        from coldfront.core.allocation.models import (
            Allocation,
            AllocationAttribute,
            AllocationUser,
        )

        allocation = Allocation.objects.get(
            project=pi_project,
            status__name="Active",
            quantity=1,
            start_date=timezone.now().date(),
            end_date=end_date,
        )
        AllocationAttribute.objects.get(
            allocation_attribute_type__name="Storage Quota (GB)",
            allocation=allocation,
            value=size,
        )
        AllocationAttribute.objects.get(
            allocation_attribute_type__name="RDF Project ID",
            allocation=allocation,
            value=format_project_number_to_id(1),
        )
        AllocationUser.objects.get(
            allocation=allocation, user=pi_project.pi, status__name="Active"
        )
        ldap_create_group_mock.assert_called_once_with(project_id)
