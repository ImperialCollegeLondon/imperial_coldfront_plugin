"""Module for performing operations in Active Directory via LDAP."""

from functools import wraps

import ldap3
from django.conf import settings
from django_q.tasks import async_task
from ldap3 import Connection, Server

LDAP_GROUP_TYPE = -2147483646  # magic number


def _get_ldap_connection():
    server = Server(settings.LDAP_URI, mode="IP_V4_ONLY")
    conn = Connection(
        server,
        settings.LDAP_USERNAME,
        settings.LDAP_PASSWORD,
        authentication="SIMPLE",
        client_strategy=ldap3.SAFE_SYNC,
        auto_bind=True,
    )
    return conn


class LDAPGroupCreationError(Exception):
    """Dedicated exception for errors encountered when creating an LDAP group."""


class LDAPGroupModifyError(Exception):
    """Dedicated exception for errors encountered when creating an LDAP group."""


def _ldap_create_group(group_name: str, conn: Connection | None = None):
    """Create an LDAP group."""
    if conn is None:
        conn = _get_ldap_connection()
    group_dn = f"cn={group_name},{settings.LDAP_GROUP_OU}"

    status, result, _, _ = conn.add(
        group_dn,
        object_class=["top", "group"],
        attributes=dict(
            cn=group_name,
            groupType=LDAP_GROUP_TYPE,
            sAMAccountName=group_name,
        ),
    )
    if not status:
        raise LDAPGroupCreationError(
            f"Failed to create LDAP group '{group_name}' - {result}"
        )


def run_in_background(func):
    """Wrapper to run a function.

    Note that Django q's architecture means this can't be used as a straight decorator
    and it's output must be stored as a different name from the wrapped function.
    """

    @wraps(func)
    def wrapped(*args, **kwargs):
        return async_task(func, *args, **kwargs)

    return wrapped


ldap_create_group_in_background = run_in_background(_ldap_create_group)
