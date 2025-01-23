"""Tests for management commands of the plugin."""

import pytest
from django.core.management import call_command
from django.utils import timezone

from imperial_coldfront_plugin.models import GroupMembership


@pytest.mark.django_db
def test_prune_groups(research_group_factory):
    """Test the prune_groups management command."""
    _, memberships = research_group_factory(number_of_members=3)

    # [0] Old membership should expire.
    # [1] Ongoing membership should not expire.
    # [2] Default (NULL) expiration membership should not expire.

    memberships[0].expiration = timezone.now() - timezone.timedelta(days=1)
    memberships[0].save()
    memberships[1].expiration = timezone.now() + timezone.timedelta(days=1)
    memberships[1].save()

    assert GroupMembership.objects.count() == 3
    call_command("prune_groups")
    assert GroupMembership.objects.count() == 2
