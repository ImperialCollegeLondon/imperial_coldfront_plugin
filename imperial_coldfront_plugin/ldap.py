"""Module for interacting with LDAP identity provider."""

import ldap
from django.conf import settings


def get_uid_from_ldap(username: str) -> int:
    """Retrieve the UID from LDAP for a given username.

    Args:
      username: The username to search for in LDAP.

    Returns:
      The UID number associated with the given username.
    """
    conn = ldap.initialize(settings.LDAP_SERVER_URI)
    conn.set_option(ldap.OPT_REFERRALS, 0)
    conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
    conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_ALLOW)
    result = conn.search_s(
        settings.LDAP_SEARCH_BASE, ldap.SCOPE_SUBTREE, f"(cn={username})", ["uidNumber"]
    )
    return int(result[0][1]["uidNumber"][0].decode("utf-8"))
