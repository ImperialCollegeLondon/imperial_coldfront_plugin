from unittest.mock import MagicMock

import pytest
import requests

from imperial_coldfront_plugin.microsoft_graph_client import (
    MicrosoftGraphClient,
    parse_profile_data,
)


@pytest.fixture
def parsed_profile():
    """Return a dictionary of profile data as structured by the graph client."""
    return dict(
        user_type="type",
        company_name="company",
        department="dept",
        job_family="job family",
        employment_status="employment status",
        job_title=None,
    )


@pytest.fixture
def profile(parsed_profile):
    """Return a dictionary of profile data as returned by the graph API."""
    return dict(
        onPremisesExtensionAttributes=dict(
            extensionAttribute14=parsed_profile["job_family"],
            extensionAttribute6=parsed_profile["employment_status"],
        ),
        userType=parsed_profile["user_type"],
        companyName=parsed_profile["company_name"],
        department=parsed_profile["department"],
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
        BASE_URL
        + (
            f"/users/{username}@ic.ac.uk?$select=jobTitle,department,companyName"
            ",userType,onPremisesExtensionAttributes"
        )
    )
