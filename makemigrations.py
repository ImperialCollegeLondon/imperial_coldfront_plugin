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
    ],
    # below checks do not need to pass to makemigrations
    SILENCED_SYSTEM_CHECKS=[
        "admin.E403",
        "admin.E406",
        "admin.E408",
        "admin.E409",
        "admin.E410",
    ],
)
django.setup()

if __name__ == "__main__":
    from django.core.management import call_command

    call_command("makemigrations", *sys.argv[1:])
