"""Pytest configuration."""

from random import choices, randint
from string import ascii_lowercase

import pytest
from django.conf import settings
from django.test import Client


def pytest_configure():
    """Configure Django settings for standalone test suite execution."""
    settings.configure(
        DEBUG=True,
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
            }
        },
        ROOT_URLCONF="imperial_coldfront_plugin.urls",
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sites",
            "django.contrib.admin",
            "django.contrib.sessions",
            "mozilla_django_oidc",
            "coldfront.core.user",
            "imperial_coldfront_plugin",
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
    )


def random_string(length=10):
    """Return a random string."""
    return "".join(choices(ascii_lowercase, k=length))


# flexible factory fixtures for more complex test cases
@pytest.fixture
def user_factory(django_user_model):
    """Provides a factory for Django users."""

    def create_user(username=None, is_pi=False, is_superuser=False):
        user = django_user_model.objects.create_user(
            username=username or random_string(), is_superuser=is_superuser
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
            GroupMembership.objects.create(member=user_factory(), group=group)
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
    return user_factory(username="testuser", is_pi=True)


@pytest.fixture
def auth_client(auth_client_factory, user):
    """Return an authenticated Django test client for `user`."""
    return auth_client_factory(user)
