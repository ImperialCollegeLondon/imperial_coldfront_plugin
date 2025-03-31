"""Email sending functionality."""

from django.conf import settings
from django.core.mail import mail_admins, send_mail
from django_q.tasks import async_task


def send_email_in_background(to_addresses: list[str], subject: str, body: str):
    """Wraps Django email functionality to send emails via a Django Q task.

    Args:
        to_addresses: A list of email addresses to send the email to.
        subject: The subject of the email.
        body: The body of the email.
    """
    async_task(
        send_mail,
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        to_addresses,
        timeout=(settings.EMAIL_TIMEOUT or 0) + 1,
    )


def send_group_invite_email(invitee_email, owner, invite_url, expiration):
    """Notify a user that they have been invited to join a ResearchGroup."""
    send_email_in_background(
        [invitee_email],
        "HPC Access Invitation",
        "You've been invited to join the access group of "
        f"{owner.get_full_name()} ({owner.email})\n\n"
        f"Click the following link to accept the invitation:\n{invite_url}.\n"
        f"Your membership is due to expire on {expiration}.",
    )


def send_group_access_granted_email(user, owner):
    """Notification email that a user has been added to a ResearchGroup."""
    send_email_in_background(
        [user.email, owner.email],
        "HPC Access Granted",
        f"This email is to confirm that {user.get_full_name()} ({user.email}) has been"
        f"granted access to the HPC access group of {owner.get_full_name()}",
    )


def send_member_promotion_to_manager_email(user, owner):
    """Notification email that a user has been made a to manager in a ResearchGroup."""
    send_email_in_background(
        [user.email, owner.email],
        "HPC Access Manager Added",
        f"This email is to confirm that {user.get_full_name()} ({user.email}) has been "
        f"made a manager in the HPC access group of {owner.get_full_name()}.",
    )


def send_manager_removed_email(user, owner):
    """Notification email that a user has been removed as manager in a ResearchGroup."""
    send_email_in_background(
        [user.email, owner.email],
        "HPC Access Manager Removed",
        f"This email is to confirm that {user.get_full_name()} ({user.email}) has been "
        f"removed as a manager in the HPC access group of {owner.get_full_name()}.",
    )


def send_expiration_alert_email(user, owner, expiration):
    """Notification email that a user's access to a ResearchGroup is about to expire."""
    send_email_in_background(
        [user.email, owner.email],
        "HPC Access Expiration Alert",
        f"This email is to notify you that {user.get_full_name()} ({user.email})'s "
        f"membership in the HPC access group of {owner.get_full_name()} is due "
        f"to expire on {expiration.date()}.",
    )


def _send_discrepancy_notification(discrepancies):
    """Send email notification for discrepancies found during the consistency check."""
    if not settings.ADMINS:
        return

    message = ["LDAP Consistency Check found discrepancies that require manual review:"]
    if discrepancies.get("missing_groups"):
        message.append("\nMissing AD Groups:")
        for grp in discrepancies["missing_groups"]:
            message.append(
                f"- Group {grp['group_id']} (Project: {grp['project_name']}, Allocation ID: {grp['allocation_id']})"  # noqa: E501
            )

    if discrepancies.get("membership_discrepancies"):
        message.append("\nMembership Discrepancies:")
        for disc in discrepancies["membership_discrepancies"]:
            message.append(
                f"\nGroup {disc['group_id']} (Project: {disc['project_name']}, Allocation ID: {disc['allocation_id']})"  # noqa: E501
            )
            if disc["missing_members"]:
                message.append(
                    "  Users missing in AD group: " + ", ".join(disc["missing_members"])
                )
            if disc["extra_members"]:
                message.append(
                    "  Extra users in AD group: " + ", ".join(disc["extra_members"])
                )

    if discrepancies.get("processing_errors"):
        message.append("\nErrors encountered during processing:")
        for err in discrepancies["processing_errors"]:
            if "allocation_id" in err:
                message.append(
                    f"- Allocation ID {err['allocation_id']}: {err['error']}"
                )
            else:
                message.append(f"- {err['error']}")

    if discrepancies.get("ldap_search_errors"):
        message.append("\nLDAP Search Errors:")
        for err in discrepancies.get("ldap_search_errors", []):
            message.append(f"- Group {err.get('group_id')}: {err.get('error')}")

    mail_admins(
        subject="LDAP Consistency Check - Discrepancies Found",
        message="\n".join(message),
        fail_silently=False,
    )
