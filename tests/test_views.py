"""Tests for the views of the plugin."""

from datetime import datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django_q.models import Task
from pytest_django.asserts import assertRedirects, assertTemplateUsed

from imperial_coldfront_plugin.forms import ProjectCreationForm, RDFAllocationForm
from imperial_coldfront_plugin.models import CreditTransaction


class LoginRequiredMixin:
    """Mixin for tests that require a user to be logged in."""

    def test_login_required(self, client):
        """Test for redirect to the login page if the user is not logged in."""
        response = client.get(self._get_url())
        assert response.status_code == HTTPStatus.FOUND
        assert response.url.startswith(settings.LOGIN_URL)


@pytest.fixture
def get_graph_api_client_mock(mocker, parsed_profile):
    """Mock out imperial_coldfront_plugin.views.get_graph_api_client."""
    mock = mocker.patch("imperial_coldfront_plugin.views.get_graph_api_client")
    mock().user_profile.return_value = parsed_profile
    mock().user_search_by.return_value = [parsed_profile]
    return mock


class TestHomeView:
    """Test rendering of the home view.

    This set of tests does not call the view function for the home page directly as
    that is a Coldfront view. Instead, it checks the rendering logic of the template
    that we override from the plugin.
    """

    @pytest.fixture
    def request_(self, rf, user):
        """A request object with a user."""
        request = rf.get("/")
        request.user = user
        return request

    def test_get_standard_user(self, request_):
        """Test that the home view renders correctly for a standard user."""
        response = render(
            request_, "imperial_coldfront_plugin/overrides/authorized_home.html"
        )

        assert response.status_code == 200


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
        ProjectStatusChoice,
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
        assert isinstance(response.context["form"], ProjectCreationForm)

    def test_post(self, superuser_client, user, settings):
        """Test posting with valid data."""
        from coldfront.core.field_of_science.models import FieldOfScience
        from coldfront.core.project.models import (
            Project,
            ProjectStatusChoice,
            ProjectUserRoleChoice,
            ProjectUserStatusChoice,
        )

        ProjectStatusChoice.objects.create(name="Active")
        project_user_status = ProjectUserStatusChoice.objects.create(name="Active")
        project_user_role = ProjectUserRoleChoice.objects.create(name="Manager")
        FieldOfScience.objects.create(pk=FieldOfScience.DEFAULT_PK)

        settings.GPFS_FILESYSTEM_NAME = "fsname"
        settings.GPFS_FILESYSTEM_MOUNT_PATH = "/mountpath"
        settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES = "top/level"
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

        project = Project.objects.get()
        assertRedirects(
            response,
            reverse(
                "project-detail",
                args=[project.pk],
            ),
            fetch_redirect_response=False,
        )

        assert project.title == title
        assert project.pi == user
        assert project.description == description

        project_user = project.projectuser_set.get()
        assert project_user.status == project_user_status
        assert project_user.role == project_user_role
        project.projectattribute_set.get
        project.projectattribute_set.get(proj_attr_type__name="Faculty", value=faculty)
        project.projectattribute_set.get(
            proj_attr_type__name="Department", value=department
        )
        group_id = project.projectattribute_set.get(
            proj_attr_type__name="Group ID", value=project.pi.username
        ).value
        project.projectattribute_set.get(
            proj_attr_type__name="Filesystem location",
            value=str(
                Path(
                    settings.GPFS_FILESYSTEM_MOUNT_PATH,
                    settings.GPFS_FILESYSTEM_NAME,
                    settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES,
                    faculty,
                    department,
                    group_id,
                )
            ),
        )
        project.projectattribute_set.get(
            proj_attr_type__name="ASK Ticket Reference", value=ticket_id
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

    def test_post_valid(self, superuser_client, project):
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
    def request_(self, rf, superuser):
        """A request object with a user."""
        request = rf.get("/")
        request.superuser = superuser
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
        content = response.content.decode("utf-8")

        assert "Credit Balance" in content
        assert "0 credits" in content

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
        content = response.content.decode("utf-8")

        assert "Credit Balance" in content
        assert "120 credits" in content
        assert "fa-coins" in content
        assert "border-primary" in content

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
        content = response.content.decode("utf-8")

        assert "Credit Balance" not in content
        assert "fa-coins" not in content


class TestProjectCreditTransactionsView:
    """Tests for the project credit transactions view."""

    def test_permission_denied_non_member(
        self, user_factory, auth_client_factory, project
    ):
        """Test that non-project members cannot access the view."""
        non_member = user_factory()
        client = auth_client_factory(non_member)

        url = reverse(
            "imperial_coldfront_plugin:project-credit-transactions",
            kwargs={"pk": project.pk},
        )
        response = client.get(url)
        assert response.status_code == 403

    def test_pi_can_access(self, client, project):
        """Test that PI can access the transactions page."""
        client.force_login(project.pi)
        url = reverse(
            "imperial_coldfront_plugin:project-credit-transactions",
            kwargs={"pk": project.pk},
        )
        response = client.get(url)
        assert response.status_code == 200

    def test_superuser_can_access(self, superuser_client, project):
        """Test that superuser can access the transactions page."""
        url = reverse(
            "imperial_coldfront_plugin:project-credit-transactions",
            kwargs={"pk": project.pk},
        )
        response = superuser_client.get(url)
        assert response.status_code == 200

    def test_transactions_dispalyed_with_total(self, superuser_client, project):
        """Test that transactions are sorted and running balance is calculated."""
        t1 = CreditTransaction.objects.create(
            project=project, amount=100, description="First"
        )
        t2 = CreditTransaction.objects.create(
            project=project, amount=50, description="Second"
        )
        t3 = CreditTransaction.objects.create(
            project=project, amount=-30, description="Third"
        )

        now = timezone.now()
        CreditTransaction.objects.filter(pk=t1.pk).update(
            timestamp=now - timedelta(days=3)
        )
        CreditTransaction.objects.filter(pk=t2.pk).update(
            timestamp=now - timedelta(days=2)
        )
        CreditTransaction.objects.filter(pk=t3.pk).update(
            timestamp=now - timedelta(days=1)
        )

        url = reverse(
            "imperial_coldfront_plugin:project-credit-transactions",
            kwargs={"pk": project.pk},
        )
        response = superuser_client.get(url)
        assert response.status_code == 200

        content = response.content.decode()

        first_pos = content.index("First")
        second_pos = content.index("Second")
        third_pos = content.index("Third")
        assert first_pos < second_pos < third_pos

        assert "100" in content
        assert "150" in content
        assert "120" in content

    def test_positive_negative_amounts_styled(self, superuser_client, project):
        """Test that positive amounts are green and negative are red."""
        CreditTransaction.objects.create(
            project=project, amount=100, description="Credit"
        )
        CreditTransaction.objects.create(
            project=project, amount=-50, description="Debit"
        )

        url = reverse(
            "imperial_coldfront_plugin:project-credit-transactions",
            kwargs={"pk": project.pk},
        )
        response = superuser_client.get(url)
        content = response.content.decode()

        assert "text-success" in content
        assert "text-danger" in content

    def test_back_link_to_project(self, superuser_client, project):
        """Test that back link to project detail exists."""
        url = reverse(
            "imperial_coldfront_plugin:project-credit-transactions",
            kwargs={"pk": project.pk},
        )
        response = superuser_client.get(url)
        content = response.content.decode()

        project_url = reverse("project-detail", kwargs={"pk": project.pk})
        assert f'href="{project_url}"' in content
        assert "Back to Project" in content
