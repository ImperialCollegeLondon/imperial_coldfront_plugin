"""Email sending functionality."""

from typing import TypedDict

from django.conf import settings
from django.core.mail import mail_admins, send_mail


class Discrepancy(TypedDict):
    """Structure for holding discrepancies found during LDAP consistency check."""

    allocation_id: int
    group_name: str
    project_name: str
    missing_members: list[str]
    extra_members: list[str]


def send_discrepancy_notification(discrepancies: list[Discrepancy]) -> None:
    """Send email notification for discrepancies found during the consistency check.

    Args:
        discrepancies: List of discrepancies found.
    """
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


def send_allocation_expiry_warning(
    allocation_shortname: str, project_owner_email: str, days_until_expiry: int
) -> None:
    """Send expiry warning notification to project owner.

    Args:
        allocation_shortname: The allocation shortname.
        project_owner_email: Email address of the project owner.
        days_until_expiry: Number of days until the allocation expires.
    """
    subject = f"RDF Allocation Expiry Warning - {days_until_expiry} days remaining"
    message = f"""
Your RDF allocation {allocation_shortname} will expire in {days_until_expiry} days.

Please take necessary action to renew or backup your data.

"""
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[project_owner_email],
    )


def send_allocation_removal_warning(
    allocation_shortname: str, project_owner_email: str, days_since_expiry: int
) -> None:
    """Send removal warning notification to project owner.

    Args:
        allocation_shortname: The allocation shortname.
        project_owner_email: Email address of the project owner.
        days_since_expiry: Number of days since the allocation expired.
    """
    subject = (
        f"RDF Allocation Removal Warning - Expired {abs(days_since_expiry)} days ago"
    )
    message = f"""
Your RDF allocation {allocation_shortname} expired {abs(days_since_expiry)} days ago.

Data removal will occur soon if no action is taken.

[Placeholder text for removal warning]
"""
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[project_owner_email],
    )


def send_allocation_deletion_warning(
    allocation_shortname: str, project_owner_email: str, days_since_expiry: int
) -> None:
    """Send deletion warning notification to project owner.

    Args:
        allocation_shortname: The allocation shortname.
        project_owner_email: Email address of the project owner.
        days_since_expiry: Number of days since the allocation expired.
    """
    subject = "RDF Allocation Deletion Warning - Final Notice"
    message = f"""
Your RDF allocation {allocation_shortname} expired {abs(days_since_expiry)} days ago.

Data will be permanently deleted soon.

[Placeholder text for deletion warning]
"""
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[project_owner_email],
    )


def send_allocation_deletion_notification(
    allocation_shortname: str, project_owner_email: str
) -> None:
    """Send deletion notification to project owner.

    Args:
        allocation_shortname: The allocation shortname.
        project_owner_email: Email address of the project owner.
    """
    subject = "RDF Allocation Deleted"
    message = f"""
Your RDF allocation {allocation_shortname} has been deleted.

All associated data has been permanently removed.

[Placeholder text for deletion notification]
"""
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[project_owner_email],
    )


class QuotaDiscrepancy(TypedDict):
    """Structure for holding discrepancies found during LDAP consistency check."""

    shortname: str
    attribute_storage_quota: int | None
    fileset_storage_quota: float | None
    attribute_files_quota: int | None
    fileset_files_quota: float | None


def send_quota_discrepancy_notification(discrepancies: list[QuotaDiscrepancy]) -> None:
    """Send quota discrepancy notification to project owner.

    Args:
        discrepancies: List of discrepancies.
    """
    if not settings.ADMINS:
        return

    message = (
        "The following discrepancies were detected between Coldfront and GPFS:\n\n"
    )

    message += "Quota Discrepancies:\n"
    for discrepancy in discrepancies:
        shortname = discrepancy["shortname"]
        message += f"\n- Allocation shortname: {shortname}\n"

        if discrepancy["attribute_storage_quota"]:
            attribute_storage_quota = discrepancy["attribute_storage_quota"]
            fileset_storage_quota = discrepancy["fileset_storage_quota"]
            message += f"""
                Allocation storage quota of {attribute_storage_quota},
                 GPFS storage quota of {fileset_storage_quota}.\n"""

        if discrepancy["attribute_files_quota"]:
            attribute_files_quota = discrepancy["attribute_files_quota"]
            fileset_files_quota = discrepancy["fileset_files_quota"]
            message += f"""
                Allocation files quota of {attribute_files_quota},
                 GPFS files quota of {fileset_files_quota}.\n"""

    mail_admins(
        subject="Quota Consistency Check - Discrepancies Found",
        message=message,
    )


def send_fileset_not_found_notification(shortnames: list[str]) -> None:
    """Send notification to admins that fileset was not found.

    Args:
        shortnames: The allocation shortnames.
    """
    if not settings.ADMINS:
        return

    subject = "Filesets Not Found"
    message = "The fileset for the following allocation(s) were not found:"
    for shortname in shortnames:
        message += f"\n- {shortname}"
    mail_admins(
        subject=subject,
        message=message,
    )
