"""Email sending functionality."""

from typing import TypedDict

from django.conf import settings
from django.core.mail import mail_admins


class Discrepancy(TypedDict):
    """Structure for holding discrepancies found during LDAP consistency check."""

    allocation_id: int
    group_name: str
    project_name: str
    missing_members: list[str]
    extra_members: list[str]


def _send_discrepancy_notification(discrepancies: list[Discrepancy]) -> None:
    """Send email notification for discrepancies found during the consistency check."""
    if not settings.ADMINS:
        return

    message = "The following discrepancies were detected between Coldfront and AD:\n\n"

    message += "Membership Discrepancies:\n"
    for discrepancy in discrepancies:
        project_name = discrepancy["project_name"]
        group_id = discrepancy["group_name"]
        message += f"\n- Project: {project_name} (Group: {group_id})\n"

        if discrepancy["missing_members"]:
            message += "  Missing members (in Coldfront but not in AD):\n"
            for member in sorted(discrepancy["missing_members"]):
                message += f"    - {member}\n"

        if discrepancy["extra_members"]:
            message += "  Extra members (in AD but not in Coldfront):\n"
            for member in sorted(discrepancy["extra_members"]):
                message += f"    - {member}\n"

    mail_admins(
        subject="LDAP Consistency Check - Discrepancies Found",
        message=message,
    )
