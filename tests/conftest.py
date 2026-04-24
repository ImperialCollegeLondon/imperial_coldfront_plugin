"""Pytest configuration."""

import datetime
import pkgutil
from pathlib import Path
from random import choices
from string import ascii_lowercase
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import Client


def pytest_configure():
    """Configure Django settings for standalone test suite execution."""
    import coldfront

    from imperial_coldfront_plugin import settings as plugin_settings

    coldfront_templates_path = Path(coldfront.__path__[0]) / "templates"
    settings.configure(
        DEBUG=True,
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
            }
        },
        ROOT_URLCONF="tests.urls",
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sites",
            "django.contrib.admin",
            "django.contrib.sessions",
            "django.contrib.humanize",
            "mozilla_django_oidc",
            "coldfront.core.user",
            "coldfront.core.field_of_science",
            "coldfront.core.project",
            "coldfront.core.resource",
            "coldfront.core.allocation",
            "coldfront.core.grant",
            "coldfront.core.publication",
            "coldfront.core.research_output",
            "coldfront.core.utils",
            "imperial_coldfront_plugin",
            "django_q",
            "crispy_forms",
            "crispy_bootstrap4",
        ],
        SECRET_KEY="123",
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": ["tests/templates", str(coldfront_templates_path)],
                "APP_DIRS": True,
                "OPTIONS": {
                    "context_processors": [
                        "django.template.context_processors.debug",
                        "django.template.context_processors.request",
                        "django.contrib.auth.context_processors.auth",
                        "django.contrib.messages.context_processors.messages",
                        "django_settings_export.settings_export",
                    ]
                },
            }
        ],
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
        ],
        TOKEN_TIMEOUT=60,
        Q_CLUSTER={"sync": True},
        CRISPY_TEMPLATE_PACK="bootstrap4",
        EMAIL_DIRECTOR_PENDING_PROJECT_REVIEW_EMAIL=False,
        EMAIL_DEVELOPMENT_EMAIL_LIST=[],
        EMAIL_SENDER=None,
        EMAIL_TICKET_SYSTEM_ADDRESS="",
        EMAIL_OPT_OUT_INSTRUCTION_URL="",
        EMAIL_SIGNATURE="",
        CENTER_NAME="",
        CENTER_BASE_URL="",
        CENTER_HELP_URL="",
        ALLOCATION_ACCOUNT_ENABLED=False,
        SETTINGS_EXPORT=[
            "SHOW_CREDIT_BALANCE",
            "ENABLE_USER_GROUP_CREATION",
            "ALLOCATION_ACCOUNT_ENABLED",
            "CENTER_HELP_URL",
            "RDF_ASK_TICKET_URL",
        ],
        **{
            key: getattr(plugin_settings, key)
            for key in dir(plugin_settings)
            if key.isupper()
        }
        | dict(
            LDAP_ENABLED=True,
            LDAP_USERNAME="",
            LDAP_PASSWORD="",
            LDAP_URI="",
            GPFS_FILESET_PATH="/path/",
            GPFS_FILESYSTEM_NAME="testfs",
            GPFS_ENABLED=True,
            GPFS_API_URL="",
            GPFS_API_USERNAME="",
            GPFS_API_PASSWORD="",
            GID_RANGES=dict(
                rdf=[range(1031386, 1031405)], hx2=[range(1031406, 1031425)]
            ),
            GPFS_ALLOCATION_CREATION_SLEEP=0,
            ENABLE_RDF_ALLOCATION_LIFECYCLE=True,
            ENABLE_USER_GROUP_CREATION=True,
            RDF_ASK_TICKET_URL="http://example.com/ticket",
        ),  # override settings loaded by env var for tests
    )


def random_string(length=10):
    """Return a random string."""
    return "".join(choices(ascii_lowercase, k=length))


# flexible factory fixtures for more complex test cases
@pytest.fixture
def user_factory(django_user_model):
    """Provides a factory for Django users.

    The factory takes the following arguments:

    - username: The username of the user. If not provided, a random string is used.
    - is_pi: Whether the user is a PI. Default is False.
    - is_superuser: Whether the user is a superuser. Default is False.
    - first_name: The first name of the user. If not provided, a random string is used.
    - last_name: The last name of the user. If not provided, a random string is used.
    """

    def create_user(
        username=None,
        is_pi=False,
        is_superuser=False,
        first_name=None,
        last_name=None,
        email=None,
    ):
        user = django_user_model.objects.create_user(
            username=username or random_string(),
            is_superuser=is_superuser,
            first_name=first_name or random_string(),
            last_name=last_name or random_string(),
            email=email or f"{random_string()}@example.com",
        )
        user.userprofile.is_pi = is_pi
        user.userprofile.save()
        return user

    return create_user


@pytest.fixture
def auth_client_factory():
    """Provides a factory for authenticated Django test clients."""

    def create_auth_client(user):
        client = Client()
        client.force_login(user)
        return client

    return create_auth_client


# fixtures for simple test cases
@pytest.fixture
def user(user_factory):
    """Provides a Django user with a fixed username."""
    return user_factory(username="testuser")


@pytest.fixture
def user_client(auth_client_factory, user):
    """Return an authenticated Django test client for `user`."""
    return auth_client_factory(user)


@pytest.fixture
def parsed_profile():
    """Return a dictionary of profile data as structured by the graph client."""
    return dict(
        user_type="Member",
        company_name="company",
        department="dept",
        job_family="job family",
        entity_type="Employee",
        job_title=None,
        name="a name",
        email="email",
        username="username",
        record_status="Live",
        first_name="A",
        last_name="Name",
    )


@pytest.fixture
def profile(parsed_profile):
    """Return a dictionary of profile data as returned by the graph API."""
    return dict(
        onPremisesExtensionAttributes=dict(
            extensionAttribute14=parsed_profile["job_family"],
            extensionAttribute6=parsed_profile["entity_type"],
            extensionAttribute5=parsed_profile["record_status"],
        ),
        userType=parsed_profile["user_type"],
        companyName=parsed_profile["company_name"],
        department=parsed_profile["department"],
        displayName=parsed_profile["name"],
        mail=parsed_profile["email"],
        userPrincipalName=parsed_profile["username"] + "@ic.ac.uk",
        givenName=parsed_profile["first_name"],
        surname=parsed_profile["last_name"],
    )


@pytest.fixture
def pi_user_profile():
    """Valid user data for a PI."""
    return {
        "record_status": "Live",
        "department": "Department of Computing",
        "entity_type": "Staff",
        "username": "test_user",
        "job_title": "Professor of Computing",
    }


@pytest.fixture
def superuser(user_factory):
    """Return a superuser."""
    return user_factory(is_superuser=True)


@pytest.fixture
def superuser_client(superuser, auth_client_factory):
    """Return a client logged in as superuser."""
    return auth_client_factory(superuser)


def _get_user_fixture(request):
    """Return a user fixture."""
    return request.getfixturevalue(request.param)


@pytest.fixture
def project_active_status(db):
    """Create a ProjectStatusChoice with name='Active'."""
    from coldfront.core.project.models import ProjectStatusChoice

    return ProjectStatusChoice.objects.get_or_create(name="Active")[0]


@pytest.fixture
def field_of_science_other(db):
    """Create a FieldOfScience with description='Other'."""
    from coldfront.core.field_of_science.models import FieldOfScience

    return FieldOfScience.objects.get_or_create(description="Other")[0]


@pytest.fixture
def project_user_active_status(db):
    """Create a ProjectUserStatusChoice with name='Active'."""
    from coldfront.core.project.models import ProjectUserStatusChoice

    return ProjectUserStatusChoice.objects.get_or_create(name="Active")[0]


@pytest.fixture
def project_user_role_manager(db):
    """Create a ProjectUserRoleChoice with name='Manager'."""
    from coldfront.core.project.models import ProjectUserRoleChoice

    return ProjectUserRoleChoice.objects.get_or_create(name="Manager")[0]


@pytest.fixture
def project_factory(
    field_of_science_other,
    project_active_status,
    project_user_active_status,
    project_user_role_manager,
):
    """Provides a factory for Coldfront projects.

    The factory takes the following arguments:

    - pi: The owner of the project.
    - title: The title of the project.
    """
    from imperial_coldfront_plugin.models import ICLProject

    def create_project(
        pi,
        title="",
        description="A default description for testing.",
        department="dsde",
        faculty="foe",
        group_id=None,
        ticket_id="",
    ):
        return ICLProject.objects.create_iclproject(
            title=title or "{user.get_full_name()}'s Research Group",
            description=description,
            field_of_science=field_of_science_other,
            user=pi,
            faculty=faculty,
            department=department,
            group_id=group_id or pi.username,
            ticket_id=ticket_id,
        )

    return create_project


@pytest.fixture
def project(user, project_factory):
    """Provides a Coldfront project owned by a user."""
    project = project_factory(pi=user)
    return project


@pytest.fixture
def project_attribute_factory(db):
    """Factory for creating ProjectAttribute instances for Group ID."""
    from coldfront.core.project.models import (
        ProjectAttribute,
        ProjectAttributeType,
    )

    def create_project_attribute(
        project,
        name,
        value,
    ):
        """Create a ProjectAttribute instance."""
        attribute_type = ProjectAttributeType.objects.get(name=name)
        return ProjectAttribute.objects.create(
            project=project,
            proj_attr_type=attribute_type,
            value=value,
        )

    return create_project_attribute


@pytest.fixture
def allocation_active_status(db):
    """Fixture to create an Active AllocationStatusChoice."""
    from coldfront.core.allocation.models import AllocationStatusChoice

    return AllocationStatusChoice.objects.get_or_create(name="Active")[0]


@pytest.fixture
def allocation_inactive_status(db):
    """Fixture to create an Inactive AllocationStatusChoice."""
    from coldfront.core.allocation.models import AllocationStatusChoice

    return AllocationStatusChoice.objects.get_or_create(name="Inactive")[0]


@pytest.fixture
def allocation_user_active_status(db):
    """Fixture to create an Active AllocationUserStatusChoice."""
    from coldfront.core.allocation.models import AllocationUserStatusChoice

    return AllocationUserStatusChoice.objects.get_or_create(name="Active")[0]


@pytest.fixture
def allocation_user_inactive_status(db):
    """Fixture to create an Inctive AllocationUserStatusChoice."""
    from coldfront.core.allocation.models import AllocationUserStatusChoice

    return AllocationUserStatusChoice.objects.get_or_create(name="Inactive")[0]


@pytest.fixture
def allocation_dependencies(allocation_active_status, allocation_user_active_status):
    """Provide the database dependencies needed for allocation creation."""
    return


@pytest.fixture(autouse=True)
def ldap_connection_mock(mocker):
    """Mock LDAP connection for tests that require it."""
    return mocker.patch(
        "imperial_coldfront_plugin.ldap.Connection",
        side_effect=RuntimeError(
            "Un-mocked LDAP connection. If you see this error during a test, it means "
            "that the test is trying to use the LDAP connection without mocking it. "
            "Mock the interface to the LDAP module."
        ),
    )


@pytest.fixture
def rdf_allocation_shortname(settings):
    """Shortname applied to rdf_allocation fixture."""
    return "shorty"


@pytest.fixture
def rdf_allocation_ldap_name(settings, rdf_allocation_shortname):
    """LDAP group name associated with rdf_allocation fixture."""
    return f"{settings.LDAP_RDF_SHORTNAME_PREFIX}{rdf_allocation_shortname}"


@pytest.fixture
def rdf_allocation_gid(settings):
    """GID applied to rdf_allocation fixture."""
    return 55


@pytest.fixture
def allocation_attribute_factory(db):
    """Factory for creating AllocationAttribute instances for GID."""
    from coldfront.core.allocation.models import (
        AllocationAttribute,
        AllocationAttributeType,
    )

    def create_allocation_attribute(
        allocation,
        name,
        value,
    ):
        """Create an AllocationAttribute instance."""
        attribute_type = AllocationAttributeType.objects.get(name=name)
        return AllocationAttribute.objects.create(
            allocation=allocation,
            allocation_attribute_type=attribute_type,
            value=value,
        )

    return create_allocation_attribute


@pytest.fixture
def rdf_allocation_factory(
    project,
    allocation_active_status,
    rdf_allocation_shortname,
    rdf_allocation_gid,
    allocation_attribute_factory,
    mocker,
):
    """A Coldfront allocation representing a rdf storage allocation."""
    from coldfront.core.resource.models import Resource

    from imperial_coldfront_plugin.models import RDFAllocation

    rdf_resource = Resource.objects.get(name="RDF Active")

    def _factory(project, shortname, gid):
        allocation = RDFAllocation.objects.create(
            project=project, status=allocation_active_status
        )
        allocation.resources.add(rdf_resource)

        allocation_attribute_factory(
            allocation=allocation, name="Shortname", value=shortname
        )
        with patch(
            "imperial_coldfront_plugin.signals.ldap_gid_in_use", return_value=False
        ):
            allocation_attribute_factory(allocation=allocation, name="GID", value=gid)
        return allocation

    return _factory


@pytest.fixture
def rdf_allocation(
    rdf_allocation_factory, project, rdf_allocation_shortname, rdf_allocation_gid
):
    """A Coldfront allocation representing a rdf storage allocation."""
    return rdf_allocation_factory(
        project=project, shortname=rdf_allocation_shortname, gid=rdf_allocation_gid
    )


@pytest.fixture
def rdf_allocation_user(allocation_user_active_status, rdf_allocation, user, mocker):
    """Provides an active user for rdf_allocation fixture."""
    from coldfront.core.allocation.models import AllocationUser

    with mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_add_member_to_group",
    ):
        return AllocationUser.objects.create(
            allocation=rdf_allocation,
            user=user,
            status=allocation_user_active_status,
        )


@pytest.fixture(autouse=True)
def patch_request_session(mocker):
    """Backstop that raises an error if an un-mocked http request is attempted."""

    def f(*args, **kwargs):
        raise RuntimeError("Un-mocked HTTP request.")

    return mocker.patch("requests.Session.send", side_effect=f)


@pytest.fixture(autouse=True)
def signals_async_task_mock(mocker):
    """Mock the async_task function used in signals to run tasks synchronously."""

    def f(func, *args, **kwargs):
        if isinstance(func, str):
            func = pkgutil.resolve_name(func)
        return func(*args, **kwargs)

    return mocker.patch("imperial_coldfront_plugin.signals.async_task", f)


@pytest.fixture
def hx2_resource(db):
    """Get HX2 Resource instance."""
    from coldfront.core.resource.models import Resource

    return Resource.objects.get(name="HX2")


@pytest.fixture
def hx2_allocation_factory(
    allocation_active_status,
    hx2_resource,
    allocation_dependencies,
):
    """Factory for creating HX2Allocation instances."""

    def create_hx2_allocation(
        project, status=allocation_active_status, start_date=datetime.date.today()
    ):
        from imperial_coldfront_plugin.models import HX2Allocation

        allocation = HX2Allocation.objects.create(
            project=project, status=status, start_date=start_date
        )
        allocation.resources.add(hx2_resource)
        return allocation

    return create_hx2_allocation


@pytest.fixture
def hx2_allocation(
    project,
    hx2_allocation_factory,
):
    """A Coldfront allocation representing an HX2 RDF storage allocation."""
    return hx2_allocation_factory(project=project)


@pytest.fixture
def hx2_allocation_user(allocation_user_active_status, hx2_allocation, user, mocker):
    """Provides an active user for hx2_allocation fixture."""
    from coldfront.core.allocation.models import AllocationUser

    with mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_add_member_to_group",
    ):
        return AllocationUser.objects.create(
            allocation=hx2_allocation,
            user=user,
            status=allocation_user_active_status,
        )


@pytest.fixture(params=["rdf_allocation", "hx2_allocation"])
def rdf_or_hx2_allocation(request):
    """Fixture to provide either an RDF or HX2 allocation."""
    return request.getfixturevalue(request.param)


@pytest.fixture(params=["rdf_allocation_user", "hx2_allocation_user"])
def rdf_or_hx2_allocation_user(request):
    """Fixture to provide an AllocationUser for either an RDF or HX2 allocation."""
    return request.getfixturevalue(request.param)
