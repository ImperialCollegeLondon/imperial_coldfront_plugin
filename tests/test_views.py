"""Tests for the views of the plugin."""

from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.shortcuts import render, reverse
from django.utils import timezone
from django_q.tasks import Chain
from pytest_django.asserts import assertRedirects, assertTemplateUsed

from imperial_coldfront_plugin.forms import ProjectCreationForm, RDFAllocationForm
from imperial_coldfront_plugin.gid import get_new_gid
from imperial_coldfront_plugin.ldap import LDAP_GROUP_TYPE, group_dn_from_name
from imperial_coldfront_plugin.views import (
    format_project_number_to_id,
    get_next_rdf_project_id,
)


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
        response = render(request_, "imperial_coldfront_plugin/home.html")

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


class TestGetNextRdfProjectId:
    """Tests for the get_next_rdf_project_id utility function."""

    def test_next_id(self, project, rdf_allocation, rdf_allocation_project_number):
        """Check correct next id is generated from existing id values."""
        assert get_next_rdf_project_id() == format_project_number_to_id(
            rdf_allocation_project_number + 1
        )

    def test_first(self, db):
        """Check initial id generation."""
        assert get_next_rdf_project_id() == format_project_number_to_id(1)


class TestAddRDFStorageAllocation(LoginRequiredMixin):
    """Tests for the add_rdf_storage_allocation view."""

    @pytest.fixture(autouse=True)
    def get_graph_api_client_mock(self, mocker):
        """Mock out imperial_coldfront_plugin.forms.get_graph_api_client."""
        mock = mocker.patch("imperial_coldfront_plugin.forms.get_graph_api_client")
        mock().user_profile.return_value = dict(username=None)
        return mock

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

    @pytest.fixture
    def post_ldap_conn_mock(self, mocker):
        """Mock LDAP connection for test_post method.

        Because we pass _ldap_create_group directly to the Django Q Chain
        we can't mock the function as Django Q encounters an error pickling the mock.
        Instead for this function we mock out the ldap connection and check the raw
        arguments passed to it.
        """
        ldap_conn_mock = mocker.patch("imperial_coldfront_plugin.ldap.Connection")
        ldap_conn_mock().add.return_value = True, [[]], None, None

        return ldap_conn_mock

    @patch("imperial_coldfront_plugin.views.Chain")
    @patch("imperial_coldfront_plugin.signals.ldap_add_member_to_group_in_background")
    @patch("imperial_coldfront_plugin.gpfs_client._create_fileset_set_quota")
    def test_post(
        self,
        gpfs_task_mock,
        ldap_add_member_mock,
        chain_mock,
        post_ldap_conn_mock,
        project,
        superuser_client,
        rdf_allocation_dependencies,
        settings,
    ):
        """Test successful project creation."""
        # mock the chain to inject the group value to check the redirect later
        chain_group = "chain_group"
        chain_mock.return_value = Chain(cached=True, group=chain_group)
        end_date = timezone.datetime.max.date()
        size = 10
        faculty = "foe"
        department = "dsde"
        dart_id = "1001"
        group_name = get_next_rdf_project_id()
        gid = get_new_gid()

        # set all of these so they are not empty
        settings.GPFS_FILESYSTEM_NAME = "fsname"
        settings.GPFS_FILESYSTEM_MOUNT_PATH = "/mountpath"
        settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES = "top/level"

        response = superuser_client.post(
            self._get_url(),
            data=dict(
                username=project.pi.username,
                end_date=end_date,
                size=size,
                department=department,
                faculty=faculty,
                dart_id=dart_id,
                gid=gid,
            ),
        )
        from coldfront.core.allocation.models import (
            Allocation,
            AllocationAttribute,
            AllocationAttributeUsage,
            AllocationUser,
        )

        allocation = Allocation.objects.get(
            project=project,
            status__name="Active",
            quantity=1,
            start_date=timezone.now().date(),
            end_date=end_date,
        )
        assertRedirects(
            response,
            reverse(
                "imperial_coldfront_plugin:list_tasks",
                args=[chain_group, allocation.pk],
            ),
            fetch_redirect_response=False,
        )

        project_id = format_project_number_to_id(1)
        storage_attribute = AllocationAttribute.objects.get(
            allocation_attribute_type__name="Storage Quota (TB)",
            allocation=allocation,
            value=size,
        )
        AllocationAttributeUsage.objects.get(
            allocation_attribute=storage_attribute, value=0
        )
        files_attribute = AllocationAttribute.objects.get(
            allocation_attribute_type__name="Files Quota",
            allocation=allocation,
            value=settings.GPFS_FILES_QUOTA,
        )
        AllocationAttributeUsage.objects.get(
            allocation_attribute=files_attribute, value=0
        )
        AllocationAttribute.objects.get(
            allocation_attribute_type__name="RDF Project ID",
            allocation=allocation,
            value=format_project_number_to_id(1),
        )
        AllocationAttribute.objects.get(
            allocation_attribute_type__name="DART ID",
            allocation=allocation,
            value=dart_id,
        )
        AllocationUser.objects.get(
            allocation=allocation, user=project.pi, status__name="Active"
        )
        post_ldap_conn_mock().add.assert_called_once_with(
            group_dn_from_name(group_name),
            object_class=["top", "group"],
            attributes=dict(
                cn=group_name,
                groupType=LDAP_GROUP_TYPE,
                sAMAccountName=group_name,
                gidNumber=min(settings.GID_RANGES[0]),
            ),
        )
        ldap_add_member_mock.assert_called_once_with(
            project_id, project.pi.username, allow_already_present=True
        )

        faculty_path = Path(
            settings.GPFS_FILESYSTEM_MOUNT_PATH,
            settings.GPFS_FILESYSTEM_NAME,
            settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES,
            faculty,
        )
        relative_projects_path = Path(department)

        gpfs_task_mock.assert_called_once_with(
            filesystem_name=settings.GPFS_FILESYSTEM_NAME,
            owner_id="root",
            group_id="root",
            fileset_name=project_id,
            parent_fileset_path=faculty_path,
            relative_projects_path=relative_projects_path,
            permissions=settings.GPFS_PERMISSIONS,
            block_quota=f"{size}T",
            files_quota=settings.GPFS_FILES_QUOTA,
            parent_fileset=faculty,
        )

    def test_post_unknown_user(self, superuser_client, get_graph_api_client_mock):
        """"""

        response = superuser_client.post(
            self._get_url(),
            data=dict(username="notauser", department="dsde", faculty="foe"),
        )
        assert response.status_code == 200
        assert (
            response.context["form"].errors["username"][0]
            == "Username not found locally or in College directory."
        )

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


class TestTaskListView(LoginRequiredMixin):
    """Tests for the task_stat_view."""

    def _get_url(self, group: str = "None", allocation_pk=1):
        return reverse(
            "imperial_coldfront_plugin:list_tasks",
            kwargs={"group": group, "allocation_pk": allocation_pk},
        )

    def test_no_tasks_returned(self, superuser_client):
        """Test that the tasks returned are none."""
        response = superuser_client.get(self._get_url())
        assert response.status_code == HTTPStatus.OK
        assertTemplateUsed(response, "imperial_coldfront_plugin/task_list.html")
        assert len(response.context["queued"]) == 0
        assert len(response.context["completed"]) == 0

    def test_the_right_tasks_returned(self, superuser_client):
        """Test that the tasks returned are the right ones.

        Note that this currently only checks for completed tasks as building test data
        for queued tasks is prohibitively complex.
        """
        from datetime import datetime
        from uuid import uuid4

        from django_q.models import Task

        for g in ["test", "test", "test", "other"]:
            Task.objects.create(
                id=uuid4(),
                func="time.sleep",
                args=[16],
                started=datetime.now(),
                stopped=datetime.now(),
                group=g,
            )

        response = superuser_client.get(self._get_url("test"))
        assert response.status_code == HTTPStatus.OK
        assertTemplateUsed(response, "imperial_coldfront_plugin/task_list.html")
        assert len(response.context["completed"]) == 3


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
        response = superuser_client.get(self._get_url())
        assert response.status_code == 200
        assert isinstance(response.context["form"], ProjectCreationForm)

    def test_post(self, superuser_client, user):
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

        title = "group title"
        description = "group_description"
        response = superuser_client.post(
            self._get_url(),
            data=dict(
                title=title,
                description=description,
                username=user.username,
                field_of_science=FieldOfScience.DEFAULT_PK,
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

    def test_post_unknown_user(self, superuser_client, get_graph_api_client_mock):
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
            ),
        )
        assert response.status_code == 200
        assert (
            response.context["form"].errors["username"][0]
            == "Username not found locally or in College directory."
        )
