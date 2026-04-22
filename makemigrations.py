"""Minimal script to make migrations without a manage.py file."""

import sys

import django
import django_stubs_ext
from django.conf import settings

settings.configure(
    INSTALLED_APPS=[
        "django.contrib.auth",
        "django.contrib.admin",
        "django.contrib.contenttypes",
        "django.contrib.sites",
        "django_q",
        "imperial_coldfront_plugin",
        "coldfront.core.field_of_science",
        "coldfront.core.project",
        "coldfront.core.resource",
        "coldfront.core.allocation",
        "coldfront.core.grant",
        "coldfront.core.publication",
        "coldfront.core.research_output",
    ],
    # below checks do not need to pass to makemigrations
    SILENCED_SYSTEM_CHECKS=[
        "admin.E403",
        "admin.E406",
        "admin.E408",
        "admin.E409",
        "admin.E410",
    ],
    SECRET_KEY="secret_key",
    Q_CLUSTER={
        "timeout": 300,
        "retry": 600,
    },
    GID_RANGES=dict(hx2=[], rdf=[]),
    EMAIL_DIRECTOR_PENDING_PROJECT_REVIEW_EMAIL=False,
    ALLOCATION_SHORTNAME_MIN_LENGTH=3,
    ALLOCATION_SHORTNAME_MAX_LENGTH=12,
    GPFS_API_TIMEOUT=4,
)

django_stubs_ext.monkeypatch()
django.setup()


if __name__ == "__main__":
    from django.core.management import call_command

    call_command("makemigrations", *sys.argv[1:])
