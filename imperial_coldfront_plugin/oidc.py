"""Customisations for the OIDC authentication backend."""

from typing import Any

from django.contrib.auth.models import User
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from .microsoft_graph_client import get_graph_api_client
from .models import UnixUID


def _update_user(user: User, claims: dict[str, Any]) -> None:
    user.username = claims["preferred_username"]
    user.email = claims["email"]
    user.first_name = claims["given_name"]
    user.last_name = claims["family_name"]
    user.save()


class ICLOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    """Extension of the OIDC authentication backend for ICL auth."""

    def create_user(self, claims: dict[str, Any]) -> User:
        """Create a new user from the available claims.

        Args:
          claims: user info provided by self.get_user_info
        """
        user = super().create_user(claims)
        _update_user(user, claims)
        UnixUID.objects.create(user=user, identifier=claims["uid"])
        return user

    def update_user(self, user: User, claims: dict[str, Any]) -> User:
        """Update user data from claims.

        Args:
          user: user to update
          claims: user info provided by self.get_user_info
        """
        _update_user(user, claims)
        return user

    def get_userinfo(
        self, access_token: str, id_token: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Get concise claims data later used for user creation/update.

        We extend the superclass implementation of this method which provides data from
        the configured OIDC userinfo endpoint to include preferred_username from the
        id_token and the user's unix uid retrieved from the Microsoft Graph API.

        Args:
          access_token: for use with the Microsoft Entra graph API.
          id_token: raw user information as a b64 encoded JWT.
          payload: decoded and verified claims from the id_token.
        """
        user_info = super().get_userinfo(access_token, id_token, payload)
        username = payload["preferred_username"].removesuffix("@ic.ac.uk")
        user_info["preferred_username"] = username

        graph_client = get_graph_api_client(access_token)
        user_info["uid"] = graph_client.user_uid(username)
        return user_info
