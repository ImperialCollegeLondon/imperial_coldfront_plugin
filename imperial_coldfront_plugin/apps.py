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
        from django.conf import settings

        django_stubs_ext.monkeypatch()

        from . import signals  # noqa: F401
        from .gid import validate_gid_range_overlap, validate_gid_ranges

        # Ensure GID_RANGES setting is valid
        # do it here to avoid circular import issues
        validate_gid_ranges(settings.GID_RANGES["hx2"])
        validate_gid_ranges(settings.GID_RANGES["rdf"])
        validate_gid_range_overlap(settings.GID_RANGES)
