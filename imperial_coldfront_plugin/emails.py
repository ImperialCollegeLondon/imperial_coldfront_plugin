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
