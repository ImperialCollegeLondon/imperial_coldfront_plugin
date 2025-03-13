"""Pytest configuration."""

from random import choices, randint
from string import ascii_lowercase

import pytest
from django.conf import settings
from django.test import Client
from django.utils import timezone


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
            "django-crispy-forms",
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
        **{
            key: getattr(plugin_settings, key)
            for key in dir(plugin_settings)
            if key.isupper()
        }
        | dict(
            LDAP_ENABLED=True,
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
def research_group_factory(user_factory):
    """Provides a factory for research groups with optional members."""
    from imperial_coldfront_plugin.models import GroupMembership, ResearchGroup

    def create_group(number_of_members=1, owner=None):
        group = ResearchGroup.objects.create(
            owner=owner or user_factory(is_pi=True),
            gid=randint(0, 100000),
            name=random_string(),
        )
        memberships = [
            GroupMembership.objects.create(
                member=user_factory(), group=group, expiration=timezone.now()
            )
            for _ in range(number_of_members)
        ]
        return group, memberships

    return create_group


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
def pi(user_factory):
    """Provides a Django user with PI status."""
    return user_factory(username="testpi", is_pi=True)


@pytest.fixture
def pi_group(research_group_factory, pi):
    """Provides a research group with a single member."""
    return research_group_factory(owner=pi)[0]


@pytest.fixture
def pi_group_member(pi_group):
    """Provides the member of pi_group."""
    return pi_group.groupmembership_set.first().member


@pytest.fixture
def pi_group_membership(pi_group_member):
    """Provides the GroupMembership object for pi_group_member."""
    return pi_group_member.groupmembership


@pytest.fixture
def pi_group_manager(pi_group, user_factory):
    """Provides a manager for pi_group."""
    from imperial_coldfront_plugin.models import GroupMembership

    manager = user_factory(username="manager")
    GroupMembership.objects.create(
        group=pi_group,
        member=manager,
        is_manager=True,
        expiration=timezone.datetime.max,
    )
    return manager


@pytest.fixture
def user_client(auth_client_factory, user):
    """Return an authenticated Django test client for `user`."""
    return auth_client_factory(user)


@pytest.fixture
def pi_client(auth_client_factory, pi):
    """Return an authenticated Django test client for a PI."""
    return auth_client_factory(pi)


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


@pytest.fixture(params=["pi", "pi_group_manager", "superuser"])
def pi_manager_or_superuser(request):
    """Parametrized fixture providing a pi, manager or superuser."""
    return _get_user_fixture(request)


@pytest.fixture(params=["pi", "superuser"])
def pi_or_superuser(request):
    """Parametrized fixture providing a pi or superuser."""
    return _get_user_fixture(request)


@pytest.fixture(params=["pi_group_member", "pi_group_manager"])
def member_or_manager(request):
    """Parametrized fixture providing a member or manager."""
    return _get_user_fixture(request)


@pytest.fixture(params=["user", "pi_group_member"])
def user_or_member(request):
    """Parametrized fixture providing a user or member."""
    return _get_user_fixture(request)


@pytest.fixture(params=["user", "pi_group_member", "pi_group_manager"])
def user_member_or_manager(request):
    """Parametrized fixture providing a user, member or manager."""
    return _get_user_fixture(request)


@pytest.fixture(autouse=True)
def ldap_connection_mock(mocker):
    """Block connections to LDAP server and return simple dummy data."""
    mock = mocker.patch("imperial_coldfront_plugin.ldap.Connection")
    mock().add.return_value = [True, None, None, None]
    mock().search.return_value = [None, None, [dict(dn="username")], None]


@pytest.fixture
def pi_project(pi):
    """Provides a Coldfront project owned by the pi user."""
    from coldfront.core.field_of_science.models import FieldOfScience
    from coldfront.core.project.models import Project, ProjectStatusChoice

    project_active_status = ProjectStatusChoice.objects.create(name="Active")
    field_of_science_other = FieldOfScience.objects.create(description="Other")

    return Project.objects.create(
        pi=pi,
        title="project title",
        status=project_active_status,
        field_of_science=field_of_science_other,
    )


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
