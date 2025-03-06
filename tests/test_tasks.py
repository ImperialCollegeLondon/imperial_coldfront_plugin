"""Tests for the tasks of the Imperial Coldfront plugin."""

import datetime

import pytest

from imperial_coldfront_plugin.tasks import send_expiration_notifications


class TestSendExpirationNotificationsTask:
    """Tests for the send_expiration_notifications task."""

    @pytest.mark.parametrize("days", (1, 5, 30))
    def test_notification_sent_before_expiry(
        self, days, pi, pi_group_membership, mailoutbox
    ):
        """Test that a notification is sent for memberships expiring in the future."""
        pi_group_membership.expiration = datetime.date.today() + datetime.timedelta(
            days=days
        )
        pi_group_membership.save()

        send_expiration_notifications()

        email = mailoutbox[0]
        email.subject == "HPC Access Expiration Alert"
        email.to == [pi.email, pi_group_membership.group.owner.email]
        email.body == (
            f"This email is to notify you that {pi.get_full_name()} ({pi.email})'s "
            f"membership in the HPC access group of "
            f"{pi_group_membership.group.owner.get_full_name()} is due "
            f"to expire on {pi_group_membership.expiration}."
        )
