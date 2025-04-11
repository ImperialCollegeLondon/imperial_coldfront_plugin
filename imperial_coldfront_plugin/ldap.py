"""Module for performing operations in Active Directory via LDAP."""

import re

import ldap3
from coldfront.core.allocation.models import Allocation, AllocationUser
from django.conf import settings
from ldap3 import Connection, Server

from .emails import _send_discrepancy_notification
from .tasks import run_in_background

LDAP_GROUP_TYPE = -2147483646  # magic number
AD_WILL_NOT_PERFORM_ERROR_CODE = 53
AD_ENTITY_ALREADY_EXISTS_ERROR_CODE = 68


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


class LDAPUserSearchError(Exception):
    """Dedicated exception when unable to retrieve a unique DN from a username."""


def ldap_get_user_dn(username: str, conn: Connection | None = None):
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


class LDAPGroupModifyError(Exception):
    """Dedicated exception for errors encountered when creating an LDAP group."""


def _ldap_create_group(group_name: str, conn: Connection | None = None):
    """Create an LDAP group."""
    if conn is None:
        conn = _get_ldap_connection()

    status, result, _, _ = conn.add(
        group_dn_from_name(group_name),
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


def group_dn_from_name(group_name):
    """Create a full group distinguished name from a common name."""
    return f"cn={group_name},{settings.LDAP_GROUP_OU}"


def _ldap_add_member_to_group(
    group_name: str,
    member_username: str,
    allow_already_present=False,
    conn: Connection | None = None,
):
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


def _ldap_remove_member_from_group(
    group_name: str,
    member_username: str,
    allow_missing=False,
    conn: Connection | None = None,
):
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


def check_ldap_consistency():
    """Check the consistency of LDAP groups with the database."""
    discrepancies = []
    allocations = Allocation.objects.filter(
        resources__name="RDF Project Storage Space",
        status__name="Active",
        allocationattribute__allocation_attribute_type__name="RDF Project ID",
    ).distinct()

    conn = _get_ldap_connection()
    for allocation in allocations:
        group_id = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="RDF Project ID"
        ).value

        active_users = AllocationUser.objects.filter(
            allocation=allocation, status__name="Active"
        )
        expected_usernames = [au.user.username for au in active_users]

        success, _, group_search, _ = conn.search(
            settings.LDAP_GROUP_OU, f"(cn={group_id})", attributes=["member"]
        )

        actual_members = []
        for member_dn in group_search[0]["attributes"].get("member", []):
            match = re.search(r"cn=([^,]+)", member_dn, re.IGNORECASE)
            if match:
                username = match.group(1)
                actual_members.append(username)

        missing_members = set(expected_usernames) - set(actual_members)
        extra_members = set(actual_members) - set(expected_usernames)

        if missing_members or extra_members:
            discrepancies.append(
                {
                    "allocation_id": allocation.id,
                    "group_id": group_id,
                    "project_name": allocation.project.title,
                    "missing_members": list(missing_members),
                    "extra_members": list(extra_members),
                }
            )

    if discrepancies:
        _send_discrepancy_notification(discrepancies)

    return discrepancies


check_ldap_consistency_in_background = run_in_background(check_ldap_consistency)
ldap_create_group_in_background = run_in_background(_ldap_create_group)
ldap_add_member_to_group_in_background = run_in_background(_ldap_add_member_to_group)
ldap_remove_member_from_group_in_background = run_in_background(
    _ldap_remove_member_from_group
)
