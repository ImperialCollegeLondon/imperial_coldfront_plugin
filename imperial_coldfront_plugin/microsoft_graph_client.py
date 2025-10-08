"""Interface for interacting with the Microsoft Graph API.

Provides a simplified interface for making requests to the Microsoft Graph API
and parsing the responses into useful data structures. It hides the details of
interacting with the API and provides a high-level interface for operations relevant
to our use case.
"""

from typing import Any

import requests
from django.conf import settings
from uplink import Consumer, get, headers, response_handler


def _get_app_access_token() -> str:
    """Get an access token for the application to use the Microsoft Graph API.

    Fetches an access token that is enabled for app-only access i.e. not on behalf of a
    logged in user.
    """
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


def _transform_profile_data(  # type: ignore[misc]
    data: dict[str, Any],
) -> dict[str, str | None]:
    extension_attributes = data.get("onPremisesExtensionAttributes", {})
    return {
        "job_title": data.get("jobTitle"),
        "department": data.get("department"),
        "company_name": data.get("companyName"),
        "user_type": data.get("userType"),
        "job_family": extension_attributes.get("extensionAttribute14"),
        "entity_type": extension_attributes.get("extensionAttribute6"),
        "record_status": extension_attributes.get("extensionAttribute5"),
        "name": data.get("displayName"),
        "email": data.get("mail"),
        "username": data.get("userPrincipalName", "").removesuffix("@ic.ac.uk"),
        "first_name": data.get("givenName"),
        "last_name": data.get("surname"),
    }


def parse_profile_data(response: requests.Response) -> dict[str, str | None]:
    """Parse the user profile data from the API response into a useful format.

    Args:
        response: The response from the Microsoft Graph API.

    Returns: The user's profile data flattened into a convenient form.
    """
    return _transform_profile_data(response.json())


def parse_profile_data_list(response: requests.Response) -> list[dict[str, str | None]]:
    """Parse a list of user profile data from the API response into a useful format.

    Args:
        response: The response from the Microsoft Graph API.

    Returns:
        A list of users' profile data flattened into a convenient form.
    """
    data = response.json()["value"]
    return [_transform_profile_data(item) for item in data]


def build_user_search_query(
    term: str | None = None, search_by: str = "all_fields"
) -> str:
    """Builds the URL query string.

    Args:
        term: The search term to look for.
        search_by: The fields to search into. If "all_fields", it will search in
            "userPrincipalName", "displayName" and "email", otherwise it only searches
            in "userPrincipalName".

    Returns:
        The query string.
    """
    return (
        f'"displayName:{term}" OR ("userPrincipalName:{term}" OR "mail:{term}")'
        if search_by == "all_fields"
        else f'"userPrincipalName:{term}"'
    )


PROFILE_ATTRIBUTES = (
    "jobTitle,department,companyName,userType,onPremisesExtensionAttributes,displayName"
    ",mail,userPrincipalName,givenName,surname"
)
"""The attributes to request when fetching user profile data."""


class MicrosoftGraphClient(Consumer):
    """Client for interacting with the Microsoft Graph API.

    Provides an abstracted interface for making requests to the Microsoft Graph API that
    provides easy to use data structures for the responses.
    """

    @response_handler(parse_profile_data)
    @get("users/{username}@ic.ac.uk?$select=" + PROFILE_ATTRIBUTES)
    def user_profile(  # type: ignore[empty-body]
        self, username: str
    ) -> dict[str, str | None]:
        """Get the profile data for a user.

        Args:
            username: The user's username (without the @ic.ac.uk).

        Returns:
            The user's profile data.
        """
        pass

    @response_handler(parse_profile_data_list)
    @headers(dict(ConsistencyLevel="eventual"))
    @get("users?$search={query}&$select=" + PROFILE_ATTRIBUTES)
    def user_search(  # type: ignore[empty-body]
        self, query: str
    ) -> list[requests.Response]:
        """Search for a user by their display name or user principal name.

        Args:
            query: The search query string.

        Returns:
          List of user profiles matching the query.
        """

    def user_search_by(
        self, user_search_string: str | None = None, search_by: str = "all_fields"
    ) -> list[dict[str, str]]:
        """Search within a specific field.

        Args:
            user_search_string: The search term to look for.
            search_by: The fields to search into. Defaults to all fields.

        Return:
            List of users' information matching the query.
        """
        query = build_user_search_query(user_search_string, search_by)
        return self.user_search(query)


def get_graph_api_client(access_token: str | None = None) -> MicrosoftGraphClient:
    """Get a client for interacting with the Microsoft Graph API.

    Args:
        access_token: An optional access token to use for authentication. If not
            provided, an app-only access token will be fetched.

    Returns:
        A configured MicrosoftGraphClient instance.
    """
    if access_token is None:
        access_token = _get_app_access_token()

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {access_token}"})
    return MicrosoftGraphClient(
        base_url="https://graph.microsoft.com/v1.0/", client=session
    )
