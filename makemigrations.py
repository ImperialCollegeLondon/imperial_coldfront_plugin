"""Minimal script to make migrations without a manage.py file."""

import sys

import django
from django.conf import settings

settings.configure(
    INSTALLED_APPS=[
        "django.contrib.auth",
        "django.contrib.admin",
        "django.contrib.contenttypes",
        "django.contrib.sites",
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
)

django.setup()

if __name__ == "__main__":
    from django.core.management import call_command

    call_command("makemigrations", *sys.argv[1:])
