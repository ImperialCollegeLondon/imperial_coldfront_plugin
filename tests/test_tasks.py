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
        assert email.subject == "HPC Access Expiration Alert"
        assert email.to == [pi_group_membership.member.email, pi.email]
        assert email.body == (
            f"This email is to notify you that "
            f"{pi_group_membership.member.get_full_name()} "
            f"({pi_group_membership.member.email})'s "
            f"membership in the HPC access group of "
            f"{pi.get_full_name()} is due "
            f"to expire on {pi_group_membership.expiration}."
        )

    def test_no_notification_sent_for_expired_membership(
        self, pi_group_membership, mailoutbox
    ):
        """Test that no notification is sent for memberships that have expired."""
        pi_group_membership.expiration = datetime.date.today() - datetime.timedelta(
            days=1
        )
        pi_group_membership.save()

        send_expiration_notifications()

        assert len(mailoutbox) == 0

    def test_no_notification_sent_for_membership_expired_today(
        self, pi_group_membership, mailoutbox
    ):
        """Test that no notification is sent for memberships expiring today."""
        pi_group_membership.expiration = datetime.date.today()
        pi_group_membership.save()

        send_expiration_notifications()

        assert len(mailoutbox) == 0
