"""Customisations for the OIDC authentication backend."""

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from .ldap import get_uid_from_ldap
from .models import UnixUID

logger = logging.getLogger("django")


class ICLOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    """Extension of the OIDC authentication backend for ICL auth."""

    def _get_user_data_from_claims(self, claims: dict[str, Any]) -> dict[str, str]:
        return dict(
            username=claims["preferred_username"].rstrip("@ic.ac.uk"),
            email=claims["email"],
            first_name=claims["given_name"],
            last_name=claims["family_name"],
        )

    def _update_user_from_dict(self, user: User, data: dict[str, str]) -> None:
        user.username = data["username"]
        user.email = data["email"]
        user.first_name = data["first_name"]
        user.last_name = data["last_name"]

    def create_user(self, claims: dict[str, Any]) -> User:
        """Create a new user from the available claims.

        Args:
          claims: user info provided by self.get_user_info
        """
        user_data = self._get_user_data_from_claims(claims)
        username = user_data["username"]
        if settings.LDAP_SERVER_URI and settings.LDAP_SEARCH_BASE:
            try:
                uid = get_uid_from_ldap(username)
            except Exception:
                raise ValueError(
                    f"Failed to retrieve UID from LDAP for user {username}"
                )
        else:
            uid = None
            logger.warn(
                f"LDAP settings not configured, UID not retrieved for user {username}"
            )

        user = super().create_user(claims)
        self._update_user_from_dict(user, user_data)
        user.save()
        if uid is not None:
            UnixUID.objects.create(user=user, identifier=uid)
        return user

    def update_user(self, user: User, claims: dict[str, Any]) -> User:
        """Update user data from claims.

        Args:
          user: user to update
          claims: user info provided by self.get_user_info
        """
        user_data = self._get_user_data_from_claims(claims)
        self._update_user_from_dict(user, user_data)
        return user

    def get_userinfo(
        self, access_token: str, id_token: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Get concise claims data later used for user creation/update.

        We extend the superclass implementation of this method which provides data from
        the configured OIDC userinfo endpoint to include preferred_username from the
        id_token.

        Args:
          access_token: for use with the Microsoft Entra graph API.
          id_token: raw user information as a b64 encoded JWT.
          payload: decoded and verified claims from the id_token.
        """
        user_info = super().get_userinfo(access_token, id_token, payload)
        user_info["preferred_username"] = payload["preferred_username"]
        return user_info
