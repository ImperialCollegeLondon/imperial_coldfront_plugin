"""Plugin tasks."""

import datetime

from django.conf import settings
from django_q.tasks import async_task

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


def create_fileset_set_quota_background_task(
    filesystem_name: str,
    fileset_name: str,
    owner_id: str,
    group_id: str,
    path: str,
    permissions: str,
    block_quota: str,
    files_quota: str,
):
    """Create a fileset and set a quota in the requested filesystem."""
    client = GPFSClient()

    def task():
        success = client.create_fileset(
            filesystem_name, fileset_name, owner_id, group_id, path, permissions
        )

        if success:
            client.set_quota(filesystem_name, fileset_name, block_quota, files_quota)

    async_task(task)
