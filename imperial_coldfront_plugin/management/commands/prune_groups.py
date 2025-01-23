"""Django management command to prune expired group memberships."""

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from imperial_coldfront_plugin.models import GroupMembership


class Command(BaseCommand):
    """Remove expired group memberships from the database."""

    help = __doc__

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Add commandline options."""
        parser.add_argument("--debug", action="store_true")

    def handle(self, debug: bool = False, **kwargs: Any) -> None:  # type: ignore[misc]
        """Command business logic."""
        query = GroupMembership.objects.filter(expiration__lt=timezone.now())

        if debug:
            self.stdout.write(f"Pruning {query.count()} expired group memberships.")

        if query.count():
            query.delete()
