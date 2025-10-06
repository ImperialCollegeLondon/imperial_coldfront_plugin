"""Module for performing operations in Active Directory via LDAP."""

import ldap3
from django.conf import settings
from ldap3 import Connection, Server

LDAP_GROUP_TYPE = -2147483646  # magic number
AD_WILL_NOT_PERFORM_ERROR_CODE = 53
AD_ENTITY_ALREADY_EXISTS_ERROR_CODE = 68
AD_NO_SUCH_OBJECT_ERROR_CODE = 32


def _get_ldap_connection() -> Connection:
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


class LDAPUserSearchError(Exception):
    """Dedicated exception when unable to retrieve a unique DN from a username."""


def ldap_get_user_dn(username: str, conn: Connection | None = None) -> str:
    """Get the full ldap dn for a user."""
    if conn is None:
        conn = _get_ldap_connection()
    _, _, response, _ = conn.search(settings.LDAP_USER_OU, f"(cn={username})")
    if len(response) == 1:
        return response[0]["dn"]
    raise LDAPUserSearchError(
        f"Unable to retrieve unique dn for username '{username}', found {len(response)}"
    )


class LDAPGroupCreationError(Exception):
    """Dedicated exception for errors encountered when creating an LDAP group."""


class LDAPGroupDeletionError(Exception):
    """Dedicated exception for errors encountered when deleting an LDAP group."""


class LDAPGroupModifyError(Exception):
    """Dedicated exception for errors encountered when creating an LDAP group."""


def ldap_create_group(
    group_name: str, gid: int, conn: Connection | None = None
) -> None:
    """Create an LDAP group."""
    if conn is None:
        conn = _get_ldap_connection()

    status, result, _, _ = conn.add(
        group_dn_from_name(group_name),
        object_class=["top", "group"],
        attributes=dict(
            cn=group_name,
            gidNumber=gid,
            groupType=LDAP_GROUP_TYPE,
            sAMAccountName=group_name,
        ),
    )
    if not status:
        raise LDAPGroupCreationError(
            f"Failed to create LDAP group '{group_name}' - {result}"
        )


def ldap_delete_group(
    group_name: str, allow_missing: bool = False, conn: Connection | None = None
) -> None:
    """Delete an LDAP group."""
    if conn is None:
        conn = _get_ldap_connection()

    status, result, _, _ = conn.delete(group_dn_from_name(group_name))
    if not status:
        if not (allow_missing and result["result"] == AD_NO_SUCH_OBJECT_ERROR_CODE):
            raise LDAPGroupDeletionError(
                f"Failed to delete LDAP group '{group_name}' - {result}"
            )


def group_dn_from_name(group_name: str) -> str:
    """Create a full group distinguished name from a common name."""
    return f"cn={group_name},{settings.LDAP_GROUP_OU}"


def ldap_add_member_to_group(
    group_name: str,
    member_username: str,
    allow_already_present: bool = False,
    conn: Connection | None = None,
) -> None:
    """Add a member to an existing ldap group."""
    if conn is None:
        conn = _get_ldap_connection()

    try:
        member_dn = ldap_get_user_dn(member_username, conn=conn)
    except LDAPUserSearchError as e:
        raise LDAPGroupModifyError(
            "Error looking up user dn during group creation."
        ) from e

    status, result, _, _ = conn.modify(
        group_dn_from_name(group_name), dict(member=(ldap3.MODIFY_ADD, [member_dn]))
    )
    if not status:
        if not (
            allow_already_present
            and result["result"] == AD_ENTITY_ALREADY_EXISTS_ERROR_CODE
        ):
            raise LDAPGroupModifyError(
                f"Failed to add member to LDAP group '{group_name}' - {result}"
            )


def ldap_remove_member_from_group(
    group_name: str,
    member_username: str,
    allow_missing: bool = False,
    conn: Connection | None = None,
) -> None:
    """Remove a member from an existing ldap group."""
    if conn is None:
        conn = _get_ldap_connection()

    try:
        member_dn = ldap_get_user_dn(member_username, conn=conn)
    except LDAPUserSearchError as e:
        raise LDAPGroupModifyError(
            "Error looking up user dn during group creation."
        ) from e

    group_dn = f"cn={group_name},{settings.LDAP_GROUP_OU}"
    status, result, _, _ = conn.modify(
        group_dn, dict(member=(ldap3.MODIFY_DELETE, [member_dn]))
    )
    if not status:
        if not (allow_missing and result["result"] == AD_WILL_NOT_PERFORM_ERROR_CODE):
            raise LDAPGroupModifyError(
                f"Failed to remove members from LDAP group '{group_name}' - {result}"
            )


def get_username_from_dn(dn: str) -> str:
    """Extract the username from a distinguished name."""
    parts = dn.split(",")
    for part in parts:
        if part.lower().startswith("cn="):
            return part[3:]
    return dn


def ldap_group_member_search(
    search_filter: str, conn: Connection | None = None
) -> dict[str, list[str]]:
    """Search for LDAP groups and return their members as a dictionary."""
    if conn is None:
        conn = _get_ldap_connection()
    _, _, response, _ = conn.search(
        settings.LDAP_GROUP_OU, f"(cn={search_filter})", attributes=["cn", "member"]
    )
    return {
        entry["attributes"]["cn"]: [
            get_username_from_dn(member_dn)
            for member_dn in entry["attributes"].get("member", [])
        ]
        for entry in response
    }


def ldap_gid_in_use(gid: int, conn: Connection | None = None) -> bool:
    """Check if a GID is already in use by any LDAP group."""
    if conn is None:
        conn = _get_ldap_connection()
    _, _, response, _ = conn.search(
        settings.LDAP_GROUP_OU, f"(gidNumber={gid})", attributes=["cn"]
    )
    return len(response) > 0
