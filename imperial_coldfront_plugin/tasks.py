"""Plugin tasks."""

import datetime

from django.conf import settings

from .emails import send_expiration_alert_email
from .gpfs_client import GPFSClient
from .models import GroupMembership


def send_expiration_notifications():
    """Notify members of upcoming group membership expirations."""
    notification_days = settings.EXPIRATION_NOTIFICATION_DAYS

    for delta_days in notification_days:
        for membership in GroupMembership.objects.filter(
            expiration=datetime.date.today() + datetime.timedelta(days=delta_days)
        ):
            group = membership.group

            send_expiration_alert_email(
                membership.member, group.owner, membership.expiration
            )


def task_create_fileset_set_quota(
    filesystem_name,
    fileset_name,
    owner_id,
    group_id,
    path,
    permissions,
    block_quota,
    files_quota,
):
    """Create fileset and set quota."""
    gpfs_client = GPFSClient()
    gpfs_client.create_fileset(
        filesystem_name,
        fileset_name,
        owner_id,
        group_id,
        path,
        permissions,
    )

    gpfs_client.set_quota(
        filesystem_name,
        fileset_name,
        block_quota,
        files_quota,
    )
