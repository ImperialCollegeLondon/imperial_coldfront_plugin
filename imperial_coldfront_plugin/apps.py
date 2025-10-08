"""Django app configuration.

This is part of the boilerplate needed for a Django app.
"""

import django_stubs_ext
from django.apps import AppConfig


class ImperialColdfrontPluginConfig(AppConfig):
    """Plugin app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "imperial_coldfront_plugin"

    def ready(self) -> None:
        """Wire up signal handlers for app."""
        from . import signals  # noqa: F401

        django_stubs_ext.monkeypatch()
