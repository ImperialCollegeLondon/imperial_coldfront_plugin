"""Tests for the tasks of the Imperial Coldfront plugin."""

import pytest


@pytest.fixture
def test_send_expiration_alert_email(mocker):
    """Fixture for testing send_expiration_alert_email."""
    return mocker.patch("imperial_coldfront_plugin.emails.send_expiration_alert_email")
