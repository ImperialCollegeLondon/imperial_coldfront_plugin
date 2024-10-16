from typing import Any

from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from django.contrib.auth.models import User


def _update_user(user: User, claims: dict[str, Any]) -> None:
    user.username = claims["preferred_username"].rstrip("@ic.ac.uk")
    user.email = claims["email"]
    user.first_name = claims["given_name"]
    user.last_name = claims["family_name"]
    user.save()


class ICLOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    def create_user(self, claims: dict[str, Any]) -> User:
        user = super().create_user(claims)
        _update_user(user, claims)
        return user

    def update_user(self, user: User, claims: dict[str, Any]) -> User:
        _update_user(user, claims)
        return user

    def get_userinfo(
        self, access_token: str, id_token: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        user_info = super().get_userinfo(access_token, id_token, payload)
        user_info["preferred_username"] = payload["preferred_username"]
        return user_info
