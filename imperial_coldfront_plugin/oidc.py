from mozilla_django_oidc.auth import OIDCAuthenticationBackend


def _update_user(user, claims):
    user.username = claims["preferred_username"].rstrip("@ic.ac.uk")
    user.email = claims["email"]
    user.first_name = claims["given_name"]
    user.last_name = claims["family_name"]
    user.save()


class ICLOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    def create_user(self, claims):
        user = super().create_user(claims)
        _update_user(user, claims)
        return user

    def update_user(self, user, claims):
        _update_user(user, claims)
        return user

    def get_userinfo(self, access_token, id_token, payload):
        user_info = super().get_userinfo(access_token, id_token, payload)
        user_info["preferred_username"] = payload["preferred_username"]
        return user_info
