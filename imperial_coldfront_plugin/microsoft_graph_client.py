"""Interface for interacting with the Microsoft Graph API."""

import requests
from django.conf import settings
from uplink import Consumer, get, response_handler


def _get_app_access_token():
    tenant_id = settings.MICROSOFT_TENANT_ID
    response = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": settings.OIDC_RP_CLIENT_ID,
            "client_secret": settings.OIDC_RP_CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
        },
    )
    return response.json()["access_token"]


def parse_profile_data(response):
    """Parse the user profile data from the API response into a useful format."""
    data = response.json()
    extension_attributes = data.get("onPremisesExtensionAttributes", {})
    return {
        "job_title": data.get("jobTitle"),
        "department": data.get("department"),
        "company_name": data.get("companyName"),
        "user_type": data.get("userType"),
        "job_family": extension_attributes.get("extensionAttribute14"),
        "employment_status": extension_attributes.get("extensionAttribute6"),
    }


def get_uid_from_response(response):
    """Extract the Unix uid from the API response."""
    data = response.json()
    uid = data.get("onPremisesExtensionAttributes", {}).get("extensionAttribute12")
    return uid if uid is None else int(uid)


class MicrosoftGraphClient(Consumer):
    """Client for interacting with the Microsoft Graph API.

    Provides an abstracted interface for making requests to the Microsoft Graph API that
    provides easy to use data structures for the responses.
    """

    @response_handler(parse_profile_data)
    @get(
        "users/{username}@ic.ac.uk?$select=jobTitle,department,companyName,userType,onPremisesExtensionAttributes"
    )
    def user_profile(self, username: str):
        """Get the profile data for a user."""
        pass

    @response_handler(get_uid_from_response)
    @get("users/{username}@ic.ac.uk?$select=onPremisesExtensionAttributes")
    def user_uid(self, username: str):
        """Get the Unix uid for a user."""


def get_graph_api_client(access_token=None):
    """Get a client for interacting with the Microsoft Graph API."""
    if access_token is None:
        access_token = _get_app_access_token()

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {access_token}"})
    return MicrosoftGraphClient(
        base_url="https://graph.microsoft.com/v1.0/", client=session
    )
