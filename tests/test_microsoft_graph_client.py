from unittest.mock import MagicMock

import pytest
import requests

from imperial_coldfront_plugin.microsoft_graph_client import (
    PROFILE_ATTRIBUTES,
    MicrosoftGraphClient,
    parse_profile_data,
)


def test_parse_profile_data(profile, parsed_profile):
    """Test that the profile data is correctly parsed."""
    api_response = MagicMock()
    api_response.json.return_value = profile

    assert parse_profile_data(api_response) == parsed_profile


BASE_URL = "https://notasite.com"
"""Dummy base URL for client testing."""


@pytest.fixture
def send_mock(mocker, profile):
    """Return a mock of the send method of a requests session."""
    send_mock = mocker.patch.object(requests.Session, "send")
    send_mock.return_value.json.return_value = profile
    return send_mock


@pytest.fixture
def graph_client(send_mock, profile):
    """Return a MicrosoftGraphClient instance for testing."""
    return MicrosoftGraphClient(base_url=BASE_URL, client=requests.Session())


def test_client_user_profile(graph_client, parsed_profile, send_mock):
    """Test that the client correctly retrieves and transforms user profile data."""
    username = "testuser"
    data = graph_client.user_profile(username)
    assert data == parsed_profile
    send_mock.assert_called_once()
    assert send_mock.call_args[0][0].url == (
        BASE_URL + (f"/users/{username}@ic.ac.uk?$select=" + PROFILE_ATTRIBUTES)
    )


@pytest.mark.parametrize("missing", (True, False))
def test_client_user_uid(missing, graph_client, send_mock):
    """Test that the client correctly retrieves the user's uid.

    Checks behaviour when the uid is missing from the returned data.
    """
    username = "testuser"
    uid = 123456
    send_mock.return_value.json.return_value = dict(
        onPremisesExtensionAttributes=(
            dict() if missing else dict(extensionAttribute12=str(uid))
        )
    )
    assert graph_client.user_uid(username) == (None if missing else uid)
    send_mock.assert_called_once()
    assert send_mock.call_args[0][0].url == BASE_URL + (
        f"/users/{username}@ic.ac.uk?$select=onPremisesExtensionAttributes"
    )
