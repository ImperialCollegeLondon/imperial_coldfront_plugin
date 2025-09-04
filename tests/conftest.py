"""Pytest configuration."""

from random import choices
from string import ascii_lowercase

import pytest
from django.conf import settings
from django.test import Client


def pytest_configure():
    """Configure Django settings for standalone test suite execution."""
    from imperial_coldfront_plugin import settings as plugin_settings

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
            "mozilla_django_oidc",
            "coldfront.core.user",
            "coldfront.core.field_of_science",
            "coldfront.core.project",
            "coldfront.core.resource",
            "coldfront.core.allocation",
            "coldfront.core.grant",
            "coldfront.core.publication",
            "coldfront.core.research_output",
            "imperial_coldfront_plugin",
            "django_q",
            "crispy_forms",
            "crispy_bootstrap4",
        ],
        SECRET_KEY="123",
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": ["tests/templates"],
                "APP_DIRS": True,
                "OPTIONS": {
                    "context_processors": [
                        "django.template.context_processors.debug",
                        "django.template.context_processors.request",
                        "django.contrib.auth.context_processors.auth",
                        "django.contrib.messages.context_processors.messages",
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
        **{
            key: getattr(plugin_settings, key)
            for key in dir(plugin_settings)
            if key.isupper()
        }
        | dict(
            LDAP_ENABLED=True,
            GPFS_FILESET_PATH="/path/",
            GPFS_FILESYSTEM_NAME="testfs",
            GPFS_ENABLED=True,
            GID_RANGES=[range(1031386, 1031435)],
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


@pytest.fixture(params=["user", "superuser"])
def user_or_superuser(request):
    """Parametrized fixture providing a user or member."""
    return _get_user_fixture(request)


@pytest.fixture(autouse=True)
def ldap_connection_mock(mocker):
    """Block connections to LDAP server and return simple dummy data."""
    mock = mocker.patch("imperial_coldfront_plugin.ldap.Connection")
    mock().add.return_value = [True, None, None, None]

    def search_side_effect(ou, search_term):
        return None, None, [dict(dn=search_term[4:-1])], None

    mock().search.side_effect = search_side_effect

    mock().modify.return_value = [True, None, None, None]
    return mock


@pytest.fixture
def project(user):
    """Provides a Coldfront project owned by a user."""
    from coldfront.core.field_of_science.models import FieldOfScience
    from coldfront.core.project.models import (
        Project,
        ProjectAttribute,
        ProjectAttributeType,
        ProjectStatusChoice,
    )

    project_active_status = ProjectStatusChoice.objects.create(name="Active")
    field_of_science_other = FieldOfScience.objects.create(description="Other")

    project = Project.objects.create(
        pi=user,
        title=f"{user.get_full_name()}'s Research Group",
        status=project_active_status,
        field_of_science=field_of_science_other,
    )
    department_attribute_type = ProjectAttributeType.objects.get(name="Department")
    faculty_attribute_type = ProjectAttributeType.objects.get(name="Faculty")
    group_id_attribute_type = ProjectAttributeType.objects.get(name="Group ID")
    ProjectAttribute.objects.create(
        proj_attr_type=department_attribute_type, project=project, value="dsde"
    )
    ProjectAttribute.objects.create(
        proj_attr_type=faculty_attribute_type, project=project, value="foe"
    )
    ProjectAttribute.objects.create(
        proj_attr_type=group_id_attribute_type, project=project, value=user.username
    )
    return project


@pytest.fixture
def rdf_allocation_dependencies(db):
    """Provide the database dependencies needed for rdf allocation creation."""
    from coldfront.core.allocation.models import (
        AllocationAttributeType,
        AllocationStatusChoice,
        AllocationUserStatusChoice,
        AttributeType,
    )

    text_type = AttributeType.objects.get(name="Text")
    AllocationStatusChoice.objects.create(name="Active")
    AllocationAttributeType.objects.create(
        name="Storage Quota (GB)", attribute_type=text_type
    )
    AllocationUserStatusChoice.objects.create(name="Active")


@pytest.fixture
def rdf_allocation_shortname(settings):
    """Shortname applied to rdf_allocation fixture."""
    return "shorty"


@pytest.fixture
def rdf_allocation_ldap_name(settings, rdf_allocation_shortname):
    """LDAP group name associated with rdf_allocation fixture."""
    return f"{settings.LDAP_SHORTNAME_PREFIX}{rdf_allocation_shortname}"


@pytest.fixture
def rdf_allocation(project, rdf_allocation_dependencies, rdf_allocation_shortname):
    """A Coldfront allocation representing a rdf storage allocation."""
    from coldfront.core.allocation.models import (
        Allocation,
        AllocationAttribute,
        AllocationAttributeType,
        AllocationStatusChoice,
    )
    from coldfront.core.resource.models import Resource

    rdf_resource = Resource.objects.get(name="RDF Active")
    shortname_attribute_type = AllocationAttributeType.objects.get(name="Shortname")

    allocation_active_status = AllocationStatusChoice.objects.get(name="Active")
    allocation = Allocation.objects.create(
        project=project, status=allocation_active_status
    )
    allocation.resources.add(rdf_resource)

    AllocationAttribute.objects.create(
        allocation_attribute_type=shortname_attribute_type,
        allocation=allocation,
        value=rdf_allocation_shortname,
    )
    return allocation


@pytest.fixture
def allocation_user_active_status(db):
    """Create an AllocationUserStatusChoice with name='Active'."""
    from coldfront.core.allocation.models import AllocationUserStatusChoice

    return AllocationUserStatusChoice.objects.create(name="Active")


@pytest.fixture
def allocation_user(allocation_user_active_status, rdf_allocation, user):
    """Provides an active user for rdf_allocation fixture."""
    from coldfront.core.allocation.models import AllocationUser

    return AllocationUser.objects.create(
        allocation=rdf_allocation,
        user=user,
        status=allocation_user_active_status,
    )


@pytest.fixture
def allocation_attribute_factory(allocation_user):
    """Factory for creating AllocationAttribute instances for GID."""
    from coldfront.core.allocation.models import (
        AllocationAttribute,
        AllocationAttributeType,
    )

    def create_allocation_attribute(
        allocation=None,
        name=None,
        value=None,
    ):
        """Create an AllocationAttribute instance."""
        if allocation is None:
            allocation = allocation_user.allocation
        name = name or random_string()
        return AllocationAttribute.objects.create(
            allocation=allocation,
            allocation_attribute_type=AllocationAttributeType.objects.get_or_create(
                name=name, defaults={"attribute_type__name": "Text"}
            )[0],
            value=value,
        )

    return create_allocation_attribute


@pytest.fixture(autouse=True)
def patch_request_session(mocker):
    """Backstop that raises an error if an un-mocked http request is attempted."""

    def f(*args, **kwargs):
        raise RuntimeError("Un-mocked HTTP request.")

    return mocker.patch("requests.Session.send", side_effect=f)
