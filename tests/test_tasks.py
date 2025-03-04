"""Tests for the tasks of the Imperial Coldfront plugin."""

import datetime

import django.utils
import pytest

from imperial_coldfront_plugin.models import GroupMembership
from imperial_coldfront_plugin.tasks import send_expiration_notifications


@pytest.mark.django_db
def test_send_expiration_notifications(settings, mailoutbox):
    """Test the send_expiration_notifications task."""
    # Create a group membership that is about to expire.
    group_membership = GroupMembership(
        expiration=django.utils.timezone.now() + datetime.timedelta(days=1)
    )

    # Set the MEMBERSHIP_EXPIRATION_DAYS setting.
    settings.MEMBERSHIP_EXPIRATION_DAYS = 1

    # Call the task.
    send_expiration_notifications()

    # Check that the email was sent.
    assert len(mailoutbox) == 1
    email = mailoutbox[0]
    assert email.subject == "HPC Access Expiration Alert"
    assert group_membership.user.email in email.to
    assert group_membership.group.owner.email in email.to
    assert str(group_membership.expiration.date()) in email.body
