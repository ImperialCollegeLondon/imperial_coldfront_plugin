"""Tests for the tasks of the Imperial Coldfront plugin."""

import datetime

import pytest

from imperial_coldfront_plugin.emails import send_expiration_alert_email
from imperial_coldfront_plugin.tasks import send_expiration_notifications


class TestSendExpirationNotificationsTask:
    """Tests for the send_expiration_notifications task."""

    @pytest.fixture
    def test_notification_sent_one_day_before(self, mocker):
        """Test that a notification is sent for memberships that expire tomorrow."""
        mocker.patch(
            "imperial_coldfront_plugin.tasks.GroupMembership.objects.filter",
            return_value=[
                mocker.Mock(
                    expiration=datetime.date.today() + datetime.timedelta(days=1)
                )
            ],
        )

        send_expiration_notifications()

        assert send_expiration_alert_email.called
        send_expiration_alert_email.assert_called_once_with(
            mocker.ANY, mocker.ANY, mocker.ANY
        )

    @pytest.fixture
    def test_notification_sent_five_days_before(self, mocker):
        """Test that a notification is sent for memberships that expire in five days."""
        mocker.patch(
            "imperial_coldfront_plugin.tasks.GroupMembership.objects.filter",
            return_value=[
                mocker.Mock(
                    expiration=datetime.date.today() + datetime.timedelta(days=5)
                )
            ],
        )

        send_expiration_notifications()

        assert send_expiration_alert_email.called
        send_expiration_alert_email.assert_called_once_with(
            mocker.ANY, mocker.ANY, mocker.ANY
        )

    @pytest.fixture
    def test_notification_sent_thirty_days_before(self, mocker):
        """Test that a notification is sent for memberships that expire in 30 days."""
        mocker.patch(
            "imperial_coldfront_plugin.tasks.GroupMembership.objects.filter",
            return_value=[
                mocker.Mock(
                    expiration=datetime.date.today() + datetime.timedelta(days=30)
                )
            ],
        )

        send_expiration_notifications()

        assert send_expiration_alert_email.called
        send_expiration_alert_email.assert_called_once_with(
            mocker.ANY, mocker.ANY, mocker.ANY
        )

    @pytest.fixture
    def test_no_notifications_sent_expired_already(self, mocker):
        """Test that no notifications sent for memberships that have expired already."""
        mocker.patch(
            "imperial_coldfront_plugin.tasks.GroupMembership.objects.filter",
            return_value=[
                mocker.Mock(expiration="2021-01-01"),
                mocker.Mock(expiration="2021-01-02"),
            ],
        )

        send_expiration_notifications()

        assert not send_expiration_alert_email.called

    @pytest.fixture
    def test_no_notifications_sent_expire_today(self, mocker):
        """Test that no notifications are sent for memberships that expire today."""
        mocker.patch(
            "imperial_coldfront_plugin.tasks.GroupMembership.objects.filter",
            return_value=[mocker.Mock(expiration=datetime.date.today())],
        )

        send_expiration_notifications()

        assert not send_expiration_alert_email.called
