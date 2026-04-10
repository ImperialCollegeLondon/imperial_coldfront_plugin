"""Tests for the views of the plugin."""

from datetime import datetime, timedelta
from http import HTTPStatus
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from coldfront.core.allocation.models import Allocation, AllocationStatusChoice
from coldfront.core.project.models import ProjectStatusChoice
from django.conf import settings
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django_q.models import Task
from pytest_django.asserts import assertRedirects, assertTemplateUsed

from imperial_coldfront_plugin.forms import (
    AdminProjectCreationForm,
    RDFAllocationForm,
    UserProjectCreationForm,
)
from imperial_coldfront_plugin.models import CreditTransaction


class LoginRequiredMixin:
    """Mixin for tests that require a user to be logged in."""

    def test_login_required(self, client):
        """Test for redirect to the login page if the user is not logged in."""
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.FOUND
        assert response.url.startswith(settings.LOGIN_URL)


def tag_with_text_filter(tag_name, text):
    """Return a filter function for BeautifulSoup to match a tag containing text."""

    def _match(tag):
        return tag.name == tag_name and text in tag.text

    return _match


@pytest.fixture
def get_graph_api_client_mock(mocker, parsed_profile):
    """Mock out imperial_coldfront_plugin.views.get_graph_api_client."""
    mock = mocker.patch("imperial_coldfront_plugin.views.get_graph_api_client")
    mock().user_profile.return_value = parsed_profile
    mock().user_search_by.return_value = [parsed_profile]
    return mock


@pytest.fixture
def allocation_active_status():
    """Fixture for an active allocation status choice."""
    return AllocationStatusChoice.objects.create(name="Active")


class TestHomeView:
    """Test rendering of the home view.

    This set of tests does not call the view function for the home page directly as
    that is a Coldfront view. Instead, it checks the rendering logic of the template
    that we override from the plugin.
    """

    @pytest.fixture(autouse=True)
    def get_graph_api_client_mock(self, mocker, parsed_profile):
        """Mock out get_graph_api_client."""
        mock = mocker.patch(
            "imperial_coldfront_plugin.templatetags.projects.get_graph_api_client"
        )
        mock().user_profile.return_value = parsed_profile
        return mock

    @pytest.fixture(autouse=True)
    def user_eligible_to_be_pi_mock(self, mocker):
        """Mock out user_eligible_to_be_pi to return True by default."""
        return mocker.patch(
            "imperial_coldfront_plugin.templatetags.projects.user_eligible_to_be_pi",
            return_value=True,
        )

    @pytest.fixture
    def request_(self, rf, user):
        """A request object with a user."""
        request = rf.get("/")
        request.user = user
        return request

    def test_get_standard_user(self, request_, mocker, user_eligible_to_be_pi_mock):
        """Test that the home view renders correctly for a standard user."""
        user_eligible_to_be_pi_mock.return_value = False

        response = render(
            request_, "imperial_coldfront_plugin/overrides/authorized_home.html"
        )

        assert response.status_code == 200
        user_eligible_to_be_pi_mock.assert_called_once()

        soup = BeautifulSoup(response.content, "html.parser")
        assert not soup.find("a", href=reverse("project-list"))
        assert not soup.find(
            "a", href=reverse("imperial_coldfront_plugin:user_create_group")
        )

    def test_group_member(
        self,
        request_,
        project,
        mocker,
        get_graph_api_client_mock,
        user_eligible_to_be_pi_mock,
    ):
        """Test that the home view renders correctly for a group member/owner."""
        user_eligible_to_be_pi_mock.return_value = False
        response = render(
            request_,
            "imperial_coldfront_plugin/overrides/authorized_home.html",
        )
        assert response.status_code == 200
        get_graph_api_client_mock().user_profile.assert_not_called()

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("a", href=reverse("project-list"))
        assert not soup.find(
            "a", href=reverse("imperial_coldfront_plugin:user_create_group")
        )

    def test_feature_flag(self, request_, settings, get_graph_api_client_mock):
        """Test home view renders correctly when the feature flag is disabled."""
        settings.ENABLE_USER_GROUP_CREATION = False
        response = render(
            request_,
            "imperial_coldfront_plugin/overrides/authorized_home.html",
        )
        assert response.status_code == 200
        get_graph_api_client_mock().user_profile.assert_not_called()
        soup = BeautifulSoup(response.content, "html.parser")
        assert not soup.find(
            "a", href=reverse("imperial_coldfront_plugin:user_create_group")
        )

    def test_eligible_user_without_projects(
        self, request_, mocker, get_graph_api_client_mock
    ):
        """Test that PI-eligible users without projects see the self-service link."""
        response = render(
            request_,
            "imperial_coldfront_plugin/overrides/authorized_home.html",
        )

        assert response.status_code == 200
        get_graph_api_client_mock().user_profile.assert_called_once_with(
            request_.user.username
        )

        soup = BeautifulSoup(response.content, "html.parser")
        assert not soup.find("a", href=reverse("project-list"))
        assert soup.find(
            "a", href=reverse("imperial_coldfront_plugin:user_create_group")
        )

    def test_eligible_user_with_project(
        self, request_, project, mocker, get_graph_api_client_mock
    ):
        """Test that PI-eligible users with projects see the self-service link."""
        response = render(
            request_,
            "imperial_coldfront_plugin/overrides/authorized_home.html",
        )

        assert response.status_code == 200
        get_graph_api_client_mock().user_profile.assert_not_called()

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("a", href=reverse("project-list"))
        assert not soup.find(
            "a", href=reverse("imperial_coldfront_plugin:user_create_group")
        )

    def test_eligible_user_with_existing_project_membership(
        self,
        request_,
        project,
        mocker,
        get_graph_api_client_mock,
        user_factory,
    ):
        """Test PI eligible users with project membership see the self-service link."""
        user = user_factory()
        request_.user = user
        from coldfront.core.project.models import (
            ProjectUser,
            ProjectUserRoleChoice,
            ProjectUserStatusChoice,
        )

        project_user_active_status, _ = ProjectUserStatusChoice.objects.get_or_create(
            name="Active"
        )
        project_user_role_manager, _ = ProjectUserRoleChoice.objects.get_or_create(
            name="Manager"
        )
        ProjectUser.objects.create(
            user=user,
            project=project,
            role=project_user_role_manager,
            status=project_user_active_status,
        )
        response = render(
            request_,
            "imperial_coldfront_plugin/overrides/authorized_home.html",
        )

        assert response.status_code == 200
        get_graph_api_client_mock().user_profile.assert_called_once_with(user.username)

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("a", href=reverse("project-list"))
        assert soup.find(
            "a", href=reverse("imperial_coldfront_plugin:user_create_group")
        )


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


class TestAddRDFStorageAllocation(LoginRequiredMixin):
    """Tests for the add_rdf_storage_allocation view."""

    @pytest.fixture(autouse=True)
    def get_graph_api_client_mock(self, mocker):
        """Mock out imperial_coldfront_plugin.forms.get_graph_api_client."""
        mock = mocker.patch("imperial_coldfront_plugin.forms.get_graph_api_client")
        mock().user_profile.return_value = dict(username=None)
        return mock

    mock_task_id = 1

    @pytest.fixture(autouse=True)
    def async_task_mock(self, mocker):
        """Mock out async_task in favour of direct task execution."""

        def f(func, *args, **kwargs):
            func(*args, **kwargs)
            return self.mock_task_id

        return mocker.patch("imperial_coldfront_plugin.views.async_task", f)

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:add_rdf_storage_allocation")

    def test_non_admin_forbidden(self, user, auth_client_factory):
        """Test non-admin users cannot access the page."""
        client = auth_client_factory(user)
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_get(self, superuser_client):
        """Check form rendering."""
        response = superuser_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert isinstance(response.context["form"], RDFAllocationForm)

    @patch("imperial_coldfront_plugin.views.create_rdf_allocation")
    def test_post(
        self,
        create_rdf_allocation_mock,
        superuser_client,
        project,
        rdf_allocation_shortname,
    ):
        """Test successful project creation."""
        # mock the chain to inject the group value to check the redirect later
        end_date = timezone.datetime.max.date()
        start_date = timezone.now().date()
        size = 10
        description = "A longer description text."

        response = superuser_client.post(
            self._get_url(),
            data=dict(
                project=project.pk,
                start_date=start_date,
                end_date=end_date,
                size=size,
                allocation_shortname=rdf_allocation_shortname,
                description=description,
            ),
        )
        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:allocation_task_result",
                args=[self.mock_task_id, rdf_allocation_shortname],
            ),
            fetch_redirect_response=False,
        )
        create_rdf_allocation_mock.assert_called_once()
        called_args, _ = create_rdf_allocation_mock.call_args
        form_data = called_args[0]
        assert form_data["project"] == project
        assert form_data["start_date"] == start_date
        assert form_data["end_date"] == end_date
        assert form_data["size"] == size
        assert form_data["allocation_shortname"] == rdf_allocation_shortname
        assert form_data["description"] == description

    class TestLoadDepartmentsView:
        """Tests for the load_departments view."""

        def _get_url(self):
            return reverse("imperial_coldfront_plugin:load_departments")

        def test_get_departments(self, client, mocker):
            """Test that the view returns the list of departments."""
            faculty = "Engineering"
            mock_get_department_choices = mocker.patch(
                "imperial_coldfront_plugin.views.get_department_choices"
            )
            mock_get_department_choices.return_value = [
                "Computer Science",
                "Mechanical",
            ]

            response = client.get(self._get_url(), {"faculty": faculty})

            assert response.status_code == HTTPStatus.OK
            assertTemplateUsed(
                response, "imperial_coldfront_plugin/departments_list.html"
            )
            assert response.context["departments"] == ["Computer Science", "Mechanical"]
            mock_get_department_choices.assert_called_once_with(faculty)


class TestAllocationTaskResult(LoginRequiredMixin):
    """Tests for the allocation_task_result view."""

    TASK_ID = "a" * 32  # 32 chars to match the Task model id field

    def _get_url(self, task_id: str = "None", shortname: str = "shorty"):
        return reverse(
            "imperial_coldfront_plugin:allocation_task_result",
            kwargs={"task_id": task_id, "shortname": shortname},
        )

    def test_no_task_returned(self, superuser_client):
        """Test when no is task returned."""
        response = superuser_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assertTemplateUsed(
            response, "imperial_coldfront_plugin/allocation_task_result.html"
        )

    def test_task_success(self, superuser_client, rdf_allocation_shortname):
        """Test view when the task completed successfully."""
        pk = 1
        Task.objects.create(
            id=self.TASK_ID,
            success=True,
            result=pk,
            started=datetime.min,
            stopped=datetime.now(),
        )
        response = superuser_client.get(
            self._get_url(self.TASK_ID, rdf_allocation_shortname)
        )
        assert response.status_code == HTTPStatus.OK
        allocation_url = reverse("allocation-detail", kwargs=dict(allocation_pk=pk))
        assert bytes(allocation_url, "utf-8") in response.content

    def test_task_failure(self, superuser_client, rdf_allocation_shortname):
        """Test view when the task failed."""
        result = "Something went wrong"
        Task.objects.create(
            id=self.TASK_ID,
            success=False,
            result=result,
            started=datetime.min,
            stopped=datetime.now(),
        )
        response = superuser_client.get(
            self._get_url(self.TASK_ID, rdf_allocation_shortname)
        )
        assert response.status_code == HTTPStatus.OK
        assert bytes(result, "utf-8") in response.content


def test_get_or_create_project(user):
    """Test get_or_create_project function."""
    from coldfront.core.field_of_science.models import FieldOfScience
    from coldfront.core.project.models import (
        Project,
        ProjectUser,
        ProjectUserRoleChoice,
        ProjectUserStatusChoice,
    )

    from imperial_coldfront_plugin.views import get_or_create_project

    FieldOfScience.objects.create(pk=FieldOfScience.DEFAULT_PK)

    assert not Project.objects.filter(pi=user)
    assert not ProjectStatusChoice.objects.filter(name="Active")
    assert not ProjectUserRoleChoice.objects.filter(name="Manager")
    assert not ProjectUserStatusChoice.objects.filter(name="Active")

    project = get_or_create_project(user)

    assert project == Project.objects.get(pi=user)
    ProjectUser.objects.get(user=user, project=project)
    ProjectStatusChoice.objects.get(name="Active")
    ProjectUserRoleChoice.objects.get(name="Manager")
    ProjectUserStatusChoice.objects.get(name="Active")


class TestAddDartID(LoginRequiredMixin):
    """Tests for the add_dart_id_to_allocation view function."""

    def _get_url(self, allocation_pk=1):
        return reverse("imperial_coldfront_plugin:add_dart_id", args=[allocation_pk])

    def test_invalid_user(self, rdf_allocation, user_factory, auth_client_factory):
        """Test a standard user cannot access the view."""
        response = auth_client_factory(user_factory()).get(
            self._get_url(rdf_allocation.pk)
        )
        assert response.status_code == 403

    def test_get(self, rdf_allocation, allocation_user, user_client):
        """Test get method."""
        from imperial_coldfront_plugin.forms import DartIDForm

        response = user_client.get(self._get_url(rdf_allocation.pk))
        assert response.status_code == 200
        assert isinstance(response.context["form"], DartIDForm)

    def test_post(self, rdf_allocation, allocation_user, user_client):
        """Test post method."""
        dart_id = "1001"
        allocation = "RDF Storage Allocation"
        response = user_client.post(
            self._get_url(rdf_allocation.pk),
            data=dict(dart_id=dart_id, allocation=allocation),
        )
        assertRedirects(
            response,
            reverse(
                "allocation-detail",
                args=[rdf_allocation.pk],
            ),
            fetch_redirect_response=False,
        )
        from coldfront.core.allocation.models import AllocationAttribute

        AllocationAttribute.objects.get(
            allocation_attribute_type__name="DART ID",
            value=dart_id,
            allocation=rdf_allocation,
        )


class TestProjectCreation(LoginRequiredMixin):
    """Tests for the project_creation view."""

    @pytest.fixture(autouse=True)
    def get_graph_api_client_mock(self, mocker):
        """Mock out imperial_coldfront_plugin.forms.get_graph_api_client."""
        mock = mocker.patch("imperial_coldfront_plugin.forms.get_graph_api_client")
        mock().user_profile.return_value = dict(username=None)
        return mock

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:new_group")

    def test_invalid_user(self, user_client):
        """Test a standard user cannot access the view."""
        response = user_client.get(self._get_url())
        assert response.status_code == 403

    def test_get(self, superuser_client):
        """Test get method."""
        response = superuser_client.get(self._get_url())
        assert response.status_code == 200
        assert isinstance(response.context["form"], AdminProjectCreationForm)

    def test_post(self, superuser_client, user, mocker):
        """Test posting with valid data."""
        from coldfront.core.field_of_science.models import FieldOfScience

        FieldOfScience.objects.create(pk=FieldOfScience.DEFAULT_PK)
        mock_create_iclproject = mocker.patch(
            "imperial_coldfront_plugin.views.ICLProject.objects.create_iclproject"
        )
        mock_pk = 123
        mock_create_iclproject.return_value.pk = mock_pk

        faculty = "foe"
        department = "dsde"

        title = "group title"
        description = "group_description"
        ticket_id = "RQST3939393"
        response = superuser_client.post(
            self._get_url(),
            data=dict(
                title=title,
                description=description,
                username=user.username,
                field_of_science=FieldOfScience.DEFAULT_PK,
                department=department,
                faculty=faculty,
                ticket_id=ticket_id,
            ),
        )

        assertRedirects(
            response,
            reverse("project-detail", args=[mock_pk]),
            fetch_redirect_response=False,
        )
        mock_create_iclproject.assert_called_once_with(
            title=title,
            description=description,
            field_of_science=FieldOfScience.objects.get(pk=FieldOfScience.DEFAULT_PK),
            user=user,
            faculty=faculty,
            department=department,
            group_id=user.username,
            ticket_id=ticket_id,
        )

    def test_post_existing_username_group_id(self, superuser_client, user, project):
        """Test project creation is blocked if there is already a group with that id."""
        response = superuser_client.post(
            self._get_url(),
            data=dict(username=user.username, faculty="fons"),
        )
        assert response.status_code == 200
        form = response.context["form"]
        assert form.errors["group_id"] == ["Name already in use."]

    def test_post_unknown_user(self, superuser_client, get_graph_api_client_mock):
        """Test posting with an invalid username."""
        from coldfront.core.field_of_science.models import FieldOfScience

        get_graph_api_client_mock.user_profile.return_value = dict(username=None)
        FieldOfScience.objects.create(pk=FieldOfScience.DEFAULT_PK)

        response = superuser_client.post(
            self._get_url(),
            data=dict(
                title="a title",
                description="a description",
                username="whatever",
                field_of_science=FieldOfScience.DEFAULT_PK,
                faculty="fons",
            ),
        )
        assert response.status_code == 200
        assert (
            response.context["form"].errors["username"][0]
            == "Username not found locally or in College directory."
        )


class TestUserProjectCreation(LoginRequiredMixin):
    """Tests for the user_project_creation view."""

    @pytest.fixture(autouse=True)
    def get_graph_api_client_mock(self, mocker, parsed_profile):
        """Mock out imperial_coldfront_plugin.views.get_graph_api_client."""
        mock = mocker.patch("imperial_coldfront_plugin.views.get_graph_api_client")
        mock().user_profile.return_value = parsed_profile
        return mock

    @pytest.fixture(autouse=True)
    def eligible_pi_mock(self, mocker):
        """Mock the PI eligibility filter."""
        mock = mocker.patch("imperial_coldfront_plugin.views.user_eligible_to_be_pi")
        mock.return_value = True
        return mock

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:user_create_group")

    def test_get(self, user_client, eligible_pi_mock):
        """Test get method."""
        response = user_client.get(self._get_url())
        assert response.status_code == 200
        assert isinstance(response.context["form"], UserProjectCreationForm)
        eligible_pi_mock.assert_called_once()

        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form")
        assert form
        assert form.find("input", attrs={"name": "title"})
        assert form.find("textarea", attrs={"name": "description"})
        assert form.find("select", attrs={"name": "field_of_science"})
        assert form.find("select", attrs={"name": "faculty"})
        assert form.find("select", attrs={"name": "department"})
        assert not form.find("input", attrs={"name": "username"})
        assert not form.find("input", attrs={"name": "group_id"})
        assert not form.find("input", attrs={"name": "ticket_id"})

    def test_feature_flag(self, user_client, settings, eligible_pi_mock):
        """Test that the view is inaccessible when the feature flag is disabled."""
        settings.ENABLE_USER_GROUP_CREATION = False
        response = user_client.get(self._get_url())
        assert response.status_code == 403
        eligible_pi_mock.assert_not_called()

    def test_get_ineligible_user_returns_forbidden(self, user_client, eligible_pi_mock):
        """Test that ineligible users cannot access the view."""
        eligible_pi_mock.return_value = False
        response = user_client.get(self._get_url())
        assert response.status_code == 403

    def test_get_existing_pi_returns_forbidden(
        self, user_client, project, eligible_pi_mock
    ):
        """Test that existing PIs cannot access the view."""
        response = user_client.get(self._get_url())
        assert response.status_code == 403
        eligible_pi_mock.assert_not_called()

    def test_post(self, user_client, user, mocker, eligible_pi_mock):
        """Test posting with valid data."""
        from coldfront.core.field_of_science.models import FieldOfScience

        FieldOfScience.objects.create(pk=FieldOfScience.DEFAULT_PK)
        mock_create_iclproject = mocker.patch(
            "imperial_coldfront_plugin.views.ICLProject.objects.create_iclproject"
        )
        mock_pk = 123
        mock_create_iclproject.return_value.pk = mock_pk

        faculty = "foe"
        department = "dsde"
        title = "group title"
        description = "group_description"

        response = user_client.post(
            self._get_url(),
            data=dict(
                title=title,
                description=description,
                field_of_science=FieldOfScience.DEFAULT_PK,
                department=department,
                faculty=faculty,
            ),
        )

        assertRedirects(
            response,
            reverse("project-detail", args=[mock_pk]),
            fetch_redirect_response=False,
        )
        eligible_pi_mock.assert_called_once()
        mock_create_iclproject.assert_called_once_with(
            title=title,
            description=description,
            field_of_science=FieldOfScience.objects.get(pk=FieldOfScience.DEFAULT_PK),
            user=user,
            faculty=faculty,
            department=department,
            group_id=user.username,
        )

    def test_post_ineligible_user_returns_forbidden(
        self, user_client, mocker, eligible_pi_mock
    ):
        """Test that ineligible users cannot create a project."""
        eligible_pi_mock.return_value = False
        mock_create_iclproject = mocker.patch(
            "imperial_coldfront_plugin.views.ICLProject.objects.create_iclproject"
        )

        response = user_client.post(
            self._get_url(),
            data=dict(
                title="group title",
                description="group_description",
                faculty="foe",
                department="dsde",
            ),
        )

        assert response.status_code == 403
        mock_create_iclproject.assert_not_called()

    def test_post_existing_pi_returns_forbidden(
        self, user_client, project, mocker, eligible_pi_mock
    ):
        """Test that existing PIs cannot create another project."""
        mock_create_iclproject = mocker.patch(
            "imperial_coldfront_plugin.views.ICLProject.objects.create_iclproject"
        )

        response = user_client.post(
            self._get_url(),
            data=dict(
                title="group title",
                description="group_description",
                faculty="foe",
                department="dsde",
            ),
        )

        assert response.status_code == 403
        eligible_pi_mock.assert_not_called()
        mock_create_iclproject.assert_not_called()

    def test_get_superuser_bypasses_profile_and_existing_pi_checks(
        self, superuser_client, project, eligible_pi_mock, get_graph_api_client_mock
    ):
        """Test that superusers can access the view without eligibility checks."""
        response = superuser_client.get(self._get_url())

        assert response.status_code == 200
        assert isinstance(response.context["form"], UserProjectCreationForm)
        eligible_pi_mock.assert_not_called()
        get_graph_api_client_mock().user_profile.assert_not_called()


class TestCreateCreditTransaction(LoginRequiredMixin):
    """Tests for the create_credit_transaction view."""

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:create_credit_transaction")

    def test_non_admin_forbidden(self, user, auth_client_factory):
        """Test non-admin users cannot access the page."""
        client = auth_client_factory(user)
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_get(self, superuser_client):
        """Check form rendering."""
        from imperial_coldfront_plugin.forms import CreditTransactionForm

        response = superuser_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assert isinstance(response.context["form"], CreditTransactionForm)
        assertTemplateUsed(
            response, "imperial_coldfront_plugin/credit_transaction_form.html"
        )

    def test_post_valid(self, superuser_client, project, superuser):
        """Test successful credit transaction creation."""
        amount = 100
        description = "Test credit transaction"

        response = superuser_client.post(
            self._get_url(),
            data=dict(
                project=project.pk,
                amount=amount,
                description=description,
            ),
        )

        assertRedirects(
            response,
            reverse("project-detail", args=[project.pk]),
            fetch_redirect_response=False,
        )

        transaction = CreditTransaction.objects.get()
        assert transaction.project == project
        assert transaction.amount == amount
        assert transaction.description == description
        assert transaction.timestamp is not None
        assert transaction.authoriser == superuser.username

    def test_post_missing_project(self, superuser_client):
        """Test form validation failure when project is missing."""
        response = superuser_client.post(
            self._get_url(),
            data=dict(
                amount=100,
                description="Test transaction",
            ),
        )

        assert response.status_code == HTTPStatus.OK
        form = response.context["form"]
        assert not form.is_valid()
        assert "project" in form.errors

    def test_post_missing_amount(self, superuser_client, project):
        """Test form validation failure when amount is missing."""
        response = superuser_client.post(
            self._get_url(),
            data=dict(
                project=project.pk,
                description="Test transaction",
            ),
        )

        assert response.status_code == HTTPStatus.OK
        form = response.context["form"]
        assert not form.is_valid()
        assert "amount" in form.errors

    def test_post_missing_description(self, superuser_client, project):
        """Test form validation failure when description is missing."""
        response = superuser_client.post(
            self._get_url(),
            data=dict(
                project=project.pk,
                amount=100,
            ),
        )

        assert response.status_code == HTTPStatus.OK
        form = response.context["form"]
        assert not form.is_valid()
        assert "description" in form.errors


class TestProjectDetailView:
    """Tests for the project detail view."""

    @pytest.fixture
    def request_(self, rf, user):
        """A request object with a user."""
        request = rf.get("/")
        request.user = user
        return request

    def test_zero_credits_render(self, request_, project, settings):
        """Test that the project detail view renders and shows a 0 balance."""
        settings.SHOW_CREDIT_BALANCE = True

        response = render(
            request_,
            "imperial_coldfront_plugin/overrides/project_detail.html",
            context={"project": project, "settings": settings},
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.content, "html.parser")
        # do full check of the structure here then other tests can just check for
        # relevant elements
        card = soup.find("div", class_="card")  # first card in the template
        assert card["id"] == "credit-balance-card"
        assert card.find(tag_with_text_filter("h3", "Credit Balance"))
        assert card.find(tag_with_text_filter("span", "0 credits"))
        assert card.find(
            tag_with_text_filter("a", "View transactions"),
            class_="btn",
            href=reverse(
                "imperial_coldfront_plugin:project-credit-transactions",
                kwargs={"pk": project.pk},
            ),
        )

    def test_credit_balance_display_when_enabled(self, request_, project, settings):
        """Test that credit balance is displayed when SHOW_CREDIT_BALANCE is True."""
        settings.SHOW_CREDIT_BALANCE = True

        CreditTransaction.objects.create(
            project=project, amount=100, description="Initial credit"
        )
        CreditTransaction.objects.create(
            project=project, amount=50, description="Additional credit"
        )
        CreditTransaction.objects.create(
            project=project, amount=-30, description="Debit"
        )

        response = render(
            request_,
            "imperial_coldfront_plugin/overrides/project_detail.html",
            context={"project": project, "settings": settings},
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.content, "html.parser")
        card = soup.find("div", class_="card", id="credit-balance-card")
        assert card.find(tag_with_text_filter("span", "120 credits"))

    def test_credit_balance_hidden_when_disabled(self, request_, project, settings):
        """Test that credit balance is not displayed when SHOW_CREDIT_BALANCE is False."""  # noqa: E501
        settings.SHOW_CREDIT_BALANCE = False

        CreditTransaction.objects.create(
            project=project, amount=100, description="Credit"
        )

        response = render(
            request_,
            "imperial_coldfront_plugin/overrides/project_detail.html",
            context={"project": project, "settings": settings},
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert not soup.find("div", class_="card", id="credit-balance-card")

    def test_credit_balance_only_visible_to_pi_and_superuser(
        self, rf, project, settings, user_factory, superuser
    ):
        """Ensure credit balance section is only rendered for the PI and superusers."""
        settings.SHOW_CREDIT_BALANCE = True
        tmpl = "imperial_coldfront_plugin/overrides/project_detail.html"

        # non-member should not see the section
        request = rf.get("/")
        request.user = user_factory()
        response = render(
            request, tmpl, context={"project": project, "settings": settings}
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert not soup.find("div", class_="card", id="credit-balance-card")

        # project PI should see the section
        request.user = project.pi
        response = render(
            request, tmpl, context={"project": project, "settings": settings}
        )
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("div", class_="card", id="credit-balance-card")

        # superuser should see the section
        request.user = superuser
        response = render(
            request, tmpl, context={"project": project, "settings": settings}
        )
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("div", class_="card", id="credit-balance-card")


class TestProjectCreditTransactionsView(LoginRequiredMixin):
    """Tests for the project credit transactions view."""

    def _get_url(self, pk: int | None = None) -> str:
        """Return the URL for the project credit transactions view.

        If `pk` is None, a dummy pk of 1 is used so the login-required test
        can call `_get_url()` without needing a fixture.
        """
        if pk is None:
            pk = 1
        return reverse(
            "imperial_coldfront_plugin:project-credit-transactions",
            kwargs={"pk": pk},
        )

    def test_permission_denied_non_member(
        self, user_factory, auth_client_factory, project
    ):
        """Test that non-project members cannot access the view."""
        non_member = user_factory()
        client = auth_client_factory(non_member)

        url = self._get_url(project.pk)
        response = client.get(url)
        assert response.status_code == 403

    def test_pi_can_access(self, client, project):
        """Test that PI can access the transactions page."""
        client.force_login(project.pi)
        url = self._get_url(project.pk)
        response = client.get(url)
        assert response.status_code == 200

    def test_superuser_can_access(self, superuser_client, project):
        """Test that superuser can access the transactions page."""
        url = self._get_url(project.pk)
        response = superuser_client.get(url)
        assert response.status_code == 200

    def test_transactions_displayed_with_total(self, superuser_client, project):
        """Test that transactions are sorted and running balance is calculated."""
        settings.SHOW_CREDIT_BALANCE = True
        transactions = [
            CreditTransaction.objects.create(
                project=project, amount=100, description="First", authoriser="Admin"
            ),
            CreditTransaction.objects.create(
                project=project, amount=50, description="Second", authoriser="Admin"
            ),
            CreditTransaction.objects.create(
                project=project, amount=-30, description="Third", authoriser="Admin"
            ),
        ]
        now = timezone.now()

        for offset, transaction in zip([3, 2, 1], transactions):
            transaction.timestamp = now - timedelta(days=offset)
            transaction.save()

        url = self._get_url(project.pk)
        response = superuser_client.get(url)
        assert response.status_code == 200

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(
            "a",
            class_="btn",
            href=reverse("project-detail", args=[project.pk]),
            text="Back to Group",
        )
        table = soup.find("table")

        rows = table.tbody.findChildren("tr")
        assert len(rows) == len(transactions)

        total = 0
        for row, transaction in zip(rows, transactions):
            cells = row.findChildren("td")
            assert cells[2].text.strip() == transaction.authoriser
            assert cells[3].span.text.strip() == str(transaction.amount)
            total += transaction.amount
            assert cells[4].text.strip() == str(total)

        footer = table.tfoot.tr
        assert footer.find(tag_with_text_filter("th", str(total)))

    def test_positive_negative_amounts_styled(self, superuser_client, project):
        """Test that positive amounts are green and negative are red."""
        CreditTransaction.objects.create(
            project=project, amount=100, description="Credit"
        )
        CreditTransaction.objects.create(
            project=project, amount=-50, description="Debit"
        )

        url = self._get_url(project.pk)
        response = superuser_client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")
        table = soup.find("table")
        rows = table.tbody.findChildren("tr")
        assert len(rows) == 2
        assert rows[0].find("span", class_="text-success")
        assert rows[1].find("span", class_="text-danger")


class TestAllocationDetailBanners:
    """Tests for allocation detail banners."""

    tmpl = "imperial_coldfront_plugin/overrides/allocation_detail.html"

    @pytest.fixture
    def request_(self, rf, project):
        """A request object with the project PI as the user."""
        request = rf.get("/")
        request.user = project.pi
        return request

    def _render_allocation_detail(self, request_, rdf_allocation, settings):
        """Helper to render the allocation detail template."""
        return render(
            request_,
            self.tmpl,
            context={
                "settings": settings,
                "allocation": rdf_allocation,
            },
        )

    def test_banner_displayed_for_expired_allocations(
        self, request_, rdf_allocation, settings
    ):
        """Test that the expired allocation banner is displayed.

        For Expired status, the deadline is end_date + REMOVAL_DAYS.
        """
        expired_status, _ = AllocationStatusChoice.objects.get_or_create(name="Expired")
        rdf_allocation.status = expired_status
        removal_days = settings.RDF_ALLOCATION_EXPIRY_REMOVAL_DAYS
        rdf_allocation.end_date = timezone.now().date() - timedelta(days=2)
        rdf_allocation.save()

        response = self._render_allocation_detail(request_, rdf_allocation, settings)
        soup = BeautifulSoup(response.content, "html.parser")
        banner = soup.find("div", id="expired-allocation", class_="alert-info")

        assert banner
        assert "This allocation has expired and is read-only" in banner.text
        expected_days = removal_days - 2
        assert f"{expected_days} day" in banner.text

    def test_banner_displayed_for_deleted_allocations(
        self, request_, rdf_allocation, settings
    ):
        """Test that the deleted allocation banner is displayed."""
        deleted_status, _ = AllocationStatusChoice.objects.get_or_create(name="Deleted")
        rdf_allocation.status = deleted_status
        rdf_allocation.save()

        response = self._render_allocation_detail(request_, rdf_allocation, settings)
        soup = BeautifulSoup(response.content, "html.parser")
        banner = soup.find("div", id="deleted-allocation", class_="alert-danger")

        assert banner
        assert "This allocation has been deleted" in banner.text

    def test_banner_displayed_for_removed_allocations(
        self, request_, rdf_allocation, settings
    ):
        """Test that the removed allocation banner is displayed.

        For Removed status, the deadline is end_date + DELETION_DAYS.
        """
        removed_status, _ = AllocationStatusChoice.objects.get_or_create(name="Removed")
        rdf_allocation.status = removed_status
        deletion_days = settings.RDF_ALLOCATION_EXPIRY_DELETION_DAYS
        rdf_allocation.end_date = timezone.now().date() - timedelta(days=5)
        rdf_allocation.save()

        response = self._render_allocation_detail(request_, rdf_allocation, settings)
        soup = BeautifulSoup(response.content, "html.parser")
        banner = soup.find("div", id="removed-allocation", class_="alert-warning")

        assert banner
        assert "This allocation has been removed and will be deleted" in banner.text
        expected_days = deletion_days - 5
        assert f"{expected_days} day" in banner.text

    def test_banner_displayed_for_archived_allocations(
        self, request_, rdf_allocation, settings, project
    ):
        """Test that the archived allocation banner is displayed."""
        archived_status, _ = ProjectStatusChoice.objects.get_or_create(name="Archived")
        rdf_allocation.project.status = archived_status
        rdf_allocation.project.save()

        response = self._render_allocation_detail(request_, rdf_allocation, settings)
        soup = BeautifulSoup(response.content, "html.parser")
        banner = soup.find("div", id="archived-allocation", class_="alert-warning")

        assert banner
        assert (
            "This is a allocation from an archived group! You cannot make any changes."
            in banner.text
        )

    def test_no_banner_for_active_allocation(self, request_, rdf_allocation, settings):
        """Test that no banner is displayed for active allocations."""
        active_status, _ = AllocationStatusChoice.objects.get_or_create(name="Active")
        rdf_allocation.status = active_status
        rdf_allocation.save()

        response = self._render_allocation_detail(request_, rdf_allocation, settings)
        soup = BeautifulSoup(response.content, "html.parser")

        assert not soup.find("div", id="expired-allocation")
        assert not soup.find("div", id="deleted-allocation")
        assert not soup.find("div", id="removed-allocation")
        assert not soup.find("div", id="archived-allocation")


class TestUserCreateHX2AllocationView(LoginRequiredMixin):
    """Tests for the user_create_hx2_allocation view."""

    def _get_url(self):
        return reverse("imperial_coldfront_plugin:user_create_hx2_allocation")

    def test_existing_allocation(self, auth_client_factory, hx2_allocation, project):
        """Test that users with an existing allocation cannot create another."""
        client = auth_client_factory(hx2_allocation.project.pi)
        response = client.get(self._get_url())
        assert response.status_code == 200
        assert b"Unable to request HX2 Access" in response.content

    @patch("imperial_coldfront_plugin.signals.ldap_gid_in_use", return_value=False)
    @patch("imperial_coldfront_plugin.models.ldap_create_group")
    def test_post(
        self,
        ldap_create_group_mock,
        ldap_gid_in_use_mock,
        auth_client_factory,
        project,
        rdf_allocation_dependencies,
    ):
        """Test that a user can create an HX2 allocation."""
        client = auth_client_factory(project.pi)
        response = client.post(
            self._get_url(), data=dict(project=project.pk, accept_terms=True)
        )
        allocation = Allocation.objects.get(project=project, resources__name="HX2")
        assertRedirects(
            response,
            reverse("allocation-detail", kwargs=dict(allocation_pk=allocation.pk)),
            fetch_redirect_response=False,
        )

    def test_post_other_users_project(self, auth_client_factory, project, user_factory):
        """Test that user cannot create an HX2 allocation for another user's project."""
        other_user = user_factory()
        client = auth_client_factory(other_user)
        response = client.post(
            self._get_url(), data=dict(project=project.pk, accept_terms=True)
        )
        assert response.status_code == 200
        assert response.context["form"].errors["project"] == [
            "Select a valid choice. That choice is not one of the available choices."
        ]

    def test_get(self, auth_client_factory, project, user_factory, project_factory):
        """Test that the form is rendered on GET and has the correct choices."""
        project_factory(pi=user_factory(), title="Other Project")

        client = auth_client_factory(project.pi)
        response = client.get(self._get_url())
        assert response.status_code == 200
        assertTemplateUsed(
            response, "imperial_coldfront_plugin/hx2_allocation_self_creation.html"
        )
        form = response.context["form"]
        assert form.fields["project"].queryset.get() == project
        assert not form.fields["accept_terms"].initial

    def test_feature_flag(self, auth_client_factory, project, user_factory, settings):
        """Test that the view is disabled when the feature flag is off."""
        settings.ENABLE_USER_GROUP_CREATION = False
        client = auth_client_factory(project.pi)
        response = client.get(self._get_url())
        assert response.status_code == 403
