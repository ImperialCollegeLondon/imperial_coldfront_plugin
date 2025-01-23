"""Django management command to prune expired group memberships."""

from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from imperial_coldfront_plugin.models import GroupMembership


class Command(BaseCommand):
    """Remove expired group memberships from the database."""

    help = __doc__

    def handle(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
        """Command business logic."""
        query = GroupMembership.objects.filter(expiration__lt=timezone.now())
        self.stdout.write(f"Pruning {query.count()} expired group memberships.")
        query.delete()
