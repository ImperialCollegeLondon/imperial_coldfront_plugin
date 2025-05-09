import urllib
from unittest.mock import MagicMock

import pytest
import requests

from imperial_coldfront_plugin.microsoft_graph_client import (
    PROFILE_ATTRIBUTES,
    MicrosoftGraphClient,
    build_user_search_query,
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


@pytest.mark.parametrize(
    "search_by,query",
    [
        (
            "all_fields",
            '"displayName:{term}" OR ("userPrincipalName:{term}" OR "mail:{term}")',
        ),
        ("something_else", '"userPrincipalName:{term}"'),
    ],
)
def test_build_user_search_query(search_by, query):
    """Tests that the search query is created correctly."""
    term = "username"
    actual = build_user_search_query(term, search_by)
    assert actual == query.format(term=term)


@pytest.mark.parametrize(
    "search_by,query",
    [
        (
            "all_fields",
            '"displayName:{term}" OR ("userPrincipalName:{term}" OR "mail:{term}")',
        ),
        ("something_else", '"userPrincipalName:{term}"'),
    ],
)
def test_client_search_user(search_by, query, graph_client, parsed_profile, send_mock):
    """Test that the client correctly retrieves and transforms user profile data."""
    username = "testuser"
    send_mock.return_value.json.return_value = dict(value=[])
    graph_client.user_search_by(username, search_by)
    expected = (
        BASE_URL
        + f"/users?$search={urllib.parse.quote(query.format(term=username))}&$select="
        + PROFILE_ATTRIBUTES
    )
    send_mock.assert_called_once()
    assert send_mock.call_args[0][0].url == expected
