"""Django app configuration.

This is part of the boilerplate needed for a Django app.
"""

import django_stubs_ext
from django.apps import AppConfig
from django.db.utils import OperationalError, ProgrammingError


class ImperialColdfrontPluginConfig(AppConfig):
    """Plugin app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "imperial_coldfront_plugin"

    def ready(self) -> None:
        """Wire up signal handlers for app."""
        from django.conf import settings
        from django_q.models import Schedule

        from . import signals  # noqa: F401
        from .gid import validate_gid_ranges

        django_stubs_ext.monkeypatch()

        # Ensure GID_RANGES setting is valid
        # do it here to avoid circular import issues
        validate_gid_ranges(settings.GID_RANGES)

        try:
            Schedule.objects.get_or_create(
                name="RDF allocation notifications",
                defaults=dict(
                    func="imperial_coldfront_plugin.tasks.send_rdf_allocation_notifications_task",
                    schedule_type=Schedule.DAILY,
                    repeats=-1,
                ),
            )
        except (OperationalError, ProgrammingError):
            # DB not ready (e.g., during migrate)
            pass
