"""Plugin tasks."""

import logging
import time
from datetime import date, timedelta

from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
    AllocationAttributeUsage,
    AllocationStatusChoice,
    AllocationUser,
    AllocationUserStatusChoice,
)
from coldfront.core.resource.models import Resource
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .emails import (
    Discrepancy,
    QuotaDiscrepancy,
    send_allocation_deletion_notification,
    send_allocation_deletion_warning,
    send_allocation_expiry_warning,
    send_allocation_removal_warning,
    send_discrepancy_notification,
    send_fileset_not_found_notification,
    send_quota_discrepancy_notification,
)
from .forms import AllocationFormData
from .gid import get_new_gid
from .gpfs_client import FilesetPathInfo, GPFSClient, create_fileset_set_quota
from .ldap import ldap_create_group, ldap_delete_group, ldap_group_member_search


def create_rdf_allocation(form_data: AllocationFormData) -> int:
    """Create an RDF allocation from a validated RDFAllocationForm.

    Note that this function interacts with external systems.

    Returns:
        The primary key of the created Allocation.
    """
    # slightly hacky but we're in the tasks module so assume we're running as a task and
    # use django-q logger
    logger = logging.getLogger("django-q")

    storage_size_tb = form_data["size"]
    # dart_id = form_data["dart_id"]
    project = form_data["project"]
    shortname = form_data["allocation_shortname"]
    ldap_name = f"{settings.LDAP_SHORTNAME_PREFIX}{shortname}"

    shortname_attribute_type = AllocationAttributeType.objects.get(name="Shortname")
    location_attribute_type = AllocationAttributeType.objects.get(
        name="Filesystem location"
    )
    storage_quota_attribute_type = AllocationAttributeType.objects.get(
        name="Storage Quota (TB)"
    )
    files_quota_attribute_type = AllocationAttributeType.objects.get(name="Files Quota")
    gid_attribute_type = AllocationAttributeType.objects.get(name="GID")
    rdf_resource = Resource.objects.get(name="RDF Active")

    allocation_active_status = AllocationStatusChoice.objects.get(name="Active")
    allocation_user_active_status = AllocationUserStatusChoice.objects.get(
        name="Active"
    )

    faculty = project.projectattribute_set.get(proj_attr_type__name="Faculty").value
    department = project.projectattribute_set.get(
        proj_attr_type__name="Department"
    ).value
    group_id = project.projectattribute_set.get(proj_attr_type__name="Group ID").value

    logger.info("Creating initial database entries for RDF allocation.")
    with transaction.atomic():
        rdf_allocation = Allocation.objects.create(
            project=project,
            status=allocation_active_status,
            start_date=form_data["start_date"],
            end_date=form_data["end_date"],
            is_changeable=True,
            justification=form_data["description"],
        )
        rdf_allocation.resources.add(rdf_resource)

        quota_attribute = AllocationAttribute.objects.create(
            allocation_attribute_type=storage_quota_attribute_type,
            allocation=rdf_allocation,
            value=storage_size_tb,
        )
        AllocationAttributeUsage.objects.create(
            allocation_attribute=quota_attribute, value=0
        )

        files_attribute = AllocationAttribute.objects.create(
            allocation_attribute_type=files_quota_attribute_type,
            allocation=rdf_allocation,
            value=settings.GPFS_FILES_QUOTA,
        )
        AllocationAttributeUsage.objects.create(
            allocation_attribute=files_attribute, value=0
        )

        AllocationAttribute.objects.create(
            allocation_attribute_type=shortname_attribute_type,
            allocation=rdf_allocation,
            value=shortname,
        )

        gid = get_new_gid()
        # create the gid attribute now so it is reserved in the database
        # uniqueness is enforced in both database and Active Directory
        AllocationAttribute.objects.create(
            allocation_attribute_type=gid_attribute_type,
            allocation=rdf_allocation,
            value=gid,
        )

        if settings.LDAP_ENABLED:
            logger.info(f"Creating AD group {ldap_name}.")
            ldap_create_group(ldap_name, gid)

        # note that this triggers a separate background job via a signal
        # to add the user to the ldap group
        # there is no way for use to check this has succeeded
        # however the scheduled sync check should pick up any failures
        AllocationUser.objects.create(
            allocation=rdf_allocation,
            user=project.pi,
            status=allocation_user_active_status,
        )

        fileset_path_info = FilesetPathInfo(
            filesystem_mount_path=settings.GPFS_FILESYSTEM_MOUNT_PATH,
            filesystem_name=settings.GPFS_FILESYSTEM_NAME,
            top_level_directories=settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES,
            faculty=faculty,
            department=department,
            group_id=group_id,
            fileset_name=shortname,
        )
        AllocationAttribute.objects.create(
            allocation_attribute_type=location_attribute_type,
            allocation=rdf_allocation,
            value=fileset_path_info.fileset_absolute_path,
        )
        if settings.GPFS_ENABLED:
            # Wait to make sure that GFPS server has picked up changes in AD
            time.sleep(settings.GPFS_ALLOCATION_CREATION_SLEEP)
            try:
                logger.info(
                    "Creating GPFS fileset and setting quota for "
                    f"{fileset_path_info.fileset_absolute_path}."
                )
                create_fileset_set_quota(
                    fileset_path_info=fileset_path_info,
                    owner_id="root",
                    group_id=ldap_name,
                    fileset_posix_permissions=settings.GPFS_FILESET_POSIX_PERMISSIONS,
                    fileset_acl=settings.GPFS_FILESET_ACL,
                    parent_posix_permissions=settings.GPFS_PARENT_DIRECTORY_POSIX_PERMISSIONS,
                    parent_acl=settings.GPFS_PARENT_DIRECTORY_ACL,
                    block_quota=f"{storage_size_tb}T",
                    files_quota=settings.GPFS_FILES_QUOTA,
                    logger=logger,
                )
            except Exception:
                logger.error(
                    f"Error encountered whilst setting up fileset {shortname}. "
                    f"Rolling back database changes and deleting AD group {ldap_name}."
                )
                ldap_delete_group(ldap_name, allow_missing=True)
                raise
    return rdf_allocation.pk


def check_ldap_consistency() -> list[Discrepancy]:
    """Check the consistency of LDAP groups with the database."""
    if not settings.LDAP_ENABLED:
        return []

    discrepancies: list[Discrepancy] = []
    allocations = Allocation.objects.filter(
        resources__name="RDF Active",
        status__name="Active",
        allocationattribute__allocation_attribute_type__name="Shortname",
    ).distinct()

    ldap_groups = ldap_group_member_search(f"{settings.LDAP_SHORTNAME_PREFIX}*")

    for allocation in allocations:
        shortname = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Shortname"
        ).value
        group_name = f"{settings.LDAP_SHORTNAME_PREFIX}{shortname}"

        active_users = AllocationUser.objects.filter(
            allocation=allocation, status__name="Active"
        )
        expected_usernames = [au.user.username for au in active_users]

        actual_members = ldap_groups.get(group_name, [])
        missing_members = set(expected_usernames) - set(actual_members)
        extra_members = set(actual_members) - set(expected_usernames)

        if missing_members or extra_members:
            discrepancies.append(
                {
                    "allocation_id": allocation.id,
                    "group_name": group_name,
                    "project_name": allocation.project.title,
                    "missing_members": list(missing_members),
                    "extra_members": list(extra_members),
                }
            )

    if discrepancies:
        send_discrepancy_notification(discrepancies)

    return discrepancies


def update_quota_usages_task() -> None:
    """Update the usages of all quota related allocation attributes."""
    client = GPFSClient()
    usages = client.retrieve_all_fileset_quotas(settings.GPFS_FILESYSTEM_NAME)

    # use prefetch_related to reduce number of database operations
    allocations = Allocation.objects.filter(
        resources__name="RDF Active"
    ).prefetch_related("allocationattribute_set")
    # below could use some more error handling but is a reasonable first pass
    for allocation in allocations:
        rdf_id = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Shortname"
        ).value
        storage_attribute_usage = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Storage Quota (TB)"
        ).allocationattributeusage
        storage_attribute_usage.value = usages[rdf_id]["block_usage_tb"]
        storage_attribute_usage.save()
        files_attribute_usage = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Files Quota"
        ).allocationattributeusage
        files_attribute_usage.value = usages[rdf_id]["files_usage"]
        files_attribute_usage.save()


def remove_allocation_group_members(allocation_id: int) -> None:
    """Background task: remove all active members from an LDAP group.

    Args:
        allocation_id: The primary key of the allocation.
    """
    from .ldap import ldap_remove_member_from_group

    if not settings.ENABLE_RDF_ALLOCATION_LIFECYCLE:
        return

    allocation = Allocation.objects.get(pk=allocation_id)

    # Get the shortname/group_id from the allocation
    try:
        shortname = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Shortname"
        ).value
        group_id = f"{settings.LDAP_SHORTNAME_PREFIX}{shortname}"
    except AllocationAttribute.DoesNotExist:
        return

    # Get all active users from the database
    active_users = AllocationUser.objects.filter(
        allocation=allocation, status__name="Active"
    )

    # Remove each user from the LDAP group
    for allocation_user in active_users:
        ldap_remove_member_from_group(
            group_id,
            allocation_user.user.username,
            allow_missing=True,
        )


def update_allocation_status() -> None:
    """Change the status of expired allocations to "removed" or "deleted".

    There are default values in the settings for how long after an allocation's end date
    it should be marked as removed or deleted. Allocations within the two limits get
    marked as "Removed", and allocations beyond the window get marked as "Deleted".
    """
    if not settings.ENABLE_RDF_ALLOCATION_LIFECYCLE:
        return

    remove_limit = timedelta(days=settings.RDF_ALLOCATION_EXPIRY_REMOVAL_DAYS)
    delete_limit = timedelta(days=settings.RDF_ALLOCATION_EXPIRY_DELETION_DAYS)

    allocations_to_remove = Allocation.objects.filter(
        # current time - end date >= remove limit
        end_date__lte=(timezone.now() - remove_limit),
        # current time - end date < delete limit
        end_date__gt=(timezone.now() - delete_limit),
        resources__name="RDF Active",
    )
    removed_status = AllocationStatusChoice.objects.get(name="Removed")
    allocations_to_remove.update(status=removed_status)

    # Delete Allocations that end beyond deletion limit
    allocations_to_delete = Allocation.objects.filter(
        # current time - expiry date > expiry limit
        end_date__lte=(timezone.now() - delete_limit),
        resources__name="RDF Active",
    )
    deleted_status = AllocationStatusChoice.objects.get(name="Deleted")
    allocations_to_delete.update(status=deleted_status)


def check_rdf_allocation_expiry_notifications() -> None:
    """Check RDF allocations and send appropriate expiry notifications."""
    if not settings.ENABLE_RDF_ALLOCATION_LIFECYCLE:
        return
    logger = logging.getLogger("django-q")

    rdf_resource = Resource.objects.get(name="RDF Active")
    today = date.today()

    # Build date lists for each notification type
    expiry_warning_dates = [
        today + timedelta(days=days)
        for days in settings.RDF_ALLOCATION_EXPIRY_WARNING_SCHEDULE
    ]
    removal_warning_dates = [
        today + timedelta(days=days)
        for days in settings.RDF_ALLOCATION_REMOVAL_WARNING_SCHEDULE
    ]
    deletion_warning_dates = [
        today + timedelta(days=days)
        for days in settings.RDF_ALLOCATION_DELETION_WARNING_SCHEDULE
    ]
    deletion_notification_dates = [
        today + timedelta(days=days)
        for days in settings.RDF_ALLOCATION_DELETION_NOTIFICATION_SCHEDULE
    ]

    # Query for expiry warnings
    expiry_allocations = Allocation.objects.filter(
        resources=rdf_resource, end_date__in=expiry_warning_dates
    ).select_related("project", "project__pi")

    for allocation in expiry_allocations:
        days_until_expiry = (allocation.end_date - today).days
        project_owner = allocation.project.pi

        logger.info(
            f"Sending expiry warning for allocation {allocation.pk} ({days_until_expiry} days)"  # noqa:E501
        )
        send_allocation_expiry_warning(
            allocation.pk, project_owner.email, days_until_expiry
        )

    # Query for removal warnings
    removal_allocations = Allocation.objects.filter(
        resources=rdf_resource, end_date__in=removal_warning_dates
    ).select_related("project", "project__pi")

    for allocation in removal_allocations:
        days_until_expiry = (allocation.end_date - today).days
        project_owner = allocation.project.pi

        logger.info(
            f"Sending removal warning for allocation {allocation.pk} ({days_until_expiry} days)"  # noqa:E501
        )
        send_allocation_removal_warning(
            allocation.pk, project_owner.email, days_until_expiry
        )

    # Query for deletion warnings
    deletion_warning_allocations = Allocation.objects.filter(
        resources=rdf_resource, end_date__in=deletion_warning_dates
    ).select_related("project", "project__pi")

    for allocation in deletion_warning_allocations:
        days_until_expiry = (allocation.end_date - today).days
        project_owner = allocation.project.pi

        logger.info(
            f"Sending deletion warning for allocation {allocation.pk} ({days_until_expiry} days)"  # noqa:E501
        )
        send_allocation_deletion_warning(
            allocation.pk, project_owner.email, days_until_expiry
        )

    # Query for deletion notifications
    deletion_notification_allocations = Allocation.objects.filter(
        resources=rdf_resource, end_date__in=deletion_notification_dates
    ).select_related("project", "project__pi")

    for allocation in deletion_notification_allocations:
        project_owner = allocation.project.pi

        logger.info(f"Sending deletion notification for allocation {allocation.pk}")
        send_allocation_deletion_notification(allocation.pk, project_owner.email)

    logger.info(
        f"Sent {expiry_allocations.count()} expiry warnings, "
        f"{removal_allocations.count()} removal warnings, "
        f"{deletion_warning_allocations.count()} deletion warnings, "
        f"{deletion_notification_allocations.count()} deletion notifications"
    )


def zero_allocation_gpfs_quota(allocation_id: int) -> None:
    """Set the GPFS quota to zero for a single expired RDF allocation.

    Args:
        allocation_id: The primary key of the allocation.
    """
    if not settings.ENABLE_RDF_ALLOCATION_LIFECYCLE:
        return
    logger = logging.getLogger("django-q")

    if not settings.GPFS_ENABLED:
        return

    allocation = Allocation.objects.get(pk=allocation_id)

    client = GPFSClient()

    try:
        shortname = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Shortname"
        ).value
    except AllocationAttribute.DoesNotExist:
        logger.error(
            f"Could not find Shortname attribute for allocation {allocation_id}. "
            "Quota not updated."
        )
        return

    logger.info(f"Setting quota to zero for expired allocation {shortname}")

    try:
        client.set_quota(
            filesystem_name=settings.GPFS_FILESYSTEM_NAME,
            fileset_name=shortname,
            block_quota="0",
            files_quota="0",
        )
    except Exception as e:
        logger.error(f"Error setting quota to zero for allocation {shortname}: {e}")
        return

    try:
        storage_quota_attribute = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Storage Quota (TB)"
        )
        storage_quota_attribute.value = "0"
        storage_quota_attribute.save()

        files_quota_attribute = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Files Quota"
        )
        files_quota_attribute.value = "0"
        files_quota_attribute.save()
    except AllocationAttribute.DoesNotExist:
        logger.error(
            f"Could not find quota attributes for allocation {shortname}. "
            "Quota not updated."
        )
        return

    logger.info(
        f"Updated Storage Quota and Files Quota attributes to 0 for allocation {shortname}"  # noqa:E501
    )


def check_quota_consistency() -> None:
    """Check consistency of file and storage quotas between allocations and filesets.

    Compares the active allocations to ensure the matching filesets have the same
    storage and file quotas. If discrepancies are found, a notification email is sent
    to admins. Also sends a notification if any allocations are found that do not have a
    matching fileset in GPFS.
    """
    if not settings.GPFS_ENABLED:
        return

    allocations = Allocation.objects.filter(
        resources__name="RDF Active",
        status__name="Active",
        allocationattribute__allocation_attribute_type__name="Shortname",
    ).distinct()

    client = GPFSClient()
    usages = client.retrieve_all_fileset_quotas(settings.GPFS_FILESYSTEM_NAME)

    discrepancies: list[QuotaDiscrepancy] = []
    missing_filesets = []

    for allocation in allocations:
        shortname = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Shortname"
        ).value
        storage_attribute_quota: int = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Storage Quota (TB)"
        ).typed_value()
        files_attribute_quota: int = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Files Quota"
        ).typed_value()

        if shortname in usages:
            # Check for discrepancies between the allocation and fileset for both
            # storage and file quotas.
            storage_quota_discrepancy = (
                storage_attribute_quota != usages[shortname]["block_limit_tb"]
            )
            file_quota_discrepancy = (
                files_attribute_quota != usages[shortname]["files_limit"]
            )
            if storage_quota_discrepancy or file_quota_discrepancy:
                # If either are not consistent, create a discrepancy record.
                discrepancies.append(
                    {
                        "shortname": shortname,
                        "attribute_storage_quota": (
                            storage_attribute_quota
                            if storage_quota_discrepancy
                            else None
                        ),
                        "fileset_storage_quota": (
                            usages[shortname]["block_limit_tb"]
                            if storage_quota_discrepancy
                            else None
                        ),
                        "attribute_files_quota": (
                            files_attribute_quota if file_quota_discrepancy else None
                        ),
                        "fileset_files_quota": (
                            usages[shortname]["files_limit"]
                            if file_quota_discrepancy
                            else None
                        ),
                    }
                )
        else:
            # The allocation was not found in GPFS - notify admins
            missing_filesets.append(shortname)

    if discrepancies:
        send_quota_discrepancy_notification(discrepancies)

    if missing_filesets:
        send_fileset_not_found_notification(missing_filesets)


def unlink_expired_allocation_filesets() -> None:
    """Unlink GPFS filesets for RDF allocations that reached unlink threshold."""
    if not settings.ENABLE_RDF_ALLOCATION_LIFECYCLE:
        return
    if not settings.GPFS_ENABLED:
        return

    logger = logging.getLogger("django-q")
    threshold_date = date.today() - timedelta(
        days=settings.RDF_ALLOCATION_EXPIRY_UNLINK_DAYS
    )

    allocations = Allocation.objects.filter(
        resources__name="RDF Active",
        end_date=threshold_date,  # run once when it hits the configured day
    ).prefetch_related("allocationattribute_set")

    client = GPFSClient()

    for allocation in allocations:
        try:
            shortname = allocation.allocationattribute_set.get(
                allocation_attribute_type__name="Shortname"
            ).value
        except AllocationAttribute.DoesNotExist:
            logger.error(
                f"Could not find Shortname attribute for allocation {allocation.pk}. "
                "Fileset unlink skipped."
            )
            continue

        try:
            logger.info(f"Unlinking GPFS fileset for expired allocation {shortname}")
            client.unlink_fileset(
                filesystemName=settings.GPFS_FILESYSTEM_NAME,
                filesetName=shortname,
                force=True,
            )
        except Exception:
            logger.exception(f"Error unlinking fileset for allocation {shortname}")
