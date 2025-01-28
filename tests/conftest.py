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
            "imperial_coldfront_plugin",
            "django_q",
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
        ],
        TOKEN_TIMEOUT=60,
        Q_CLUSTER={"sync": True},
        **{
            key: getattr(plugin_settings, key)
            for key in dir(plugin_settings)
            if key.isupper()
        },
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
def user_client(auth_client_factory, user):
    """Return an authenticated Django test client for `user`."""
    return auth_client_factory(user)


@pytest.fixture
def pi_client(auth_client_factory, pi):
    """Return an authenticated Django test client for a PI."""
    return auth_client_factory(pi)


@pytest.fixture
def manager_in_group(user_factory, research_group_factory):
    """Return a user who is a manager in a research group."""
    from imperial_coldfront_plugin.models import GroupMembership

    manager = user_factory()
    group, memberships = research_group_factory(number_of_members=0)
    GroupMembership.objects.create(
        group=group, member=manager, is_manager=True, expiration=timezone.now()
    )
    return manager, group


@pytest.fixture
def parsed_profile():
    """Return a dictionary of profile data as structured by the graph client."""
    return dict(
        user_type="Member",
        company_name="company",
        department="dept",
        job_family="job family",
        entity_type="entity type",
        job_title=None,
        name="a name",
        email="email",
        username="username",
        record_status="Live",
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
    )
