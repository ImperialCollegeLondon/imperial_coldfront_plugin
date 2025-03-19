"""Django app configuration."""

from django.apps import AppConfig


class ImperialColdfrontPluginConfig(AppConfig):
    """Plugin app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "imperial_coldfront_plugin"

    def ready(self):
        """Wire up signal handlers for app."""
        from . import signals  # noqa: F401
