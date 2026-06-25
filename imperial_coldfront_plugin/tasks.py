"""Plugin tasks."""

import logging
import time
from datetime import date, timedelta

from coldfront.core.allocation.models import (
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
from django.db.models import QuerySet
from django.utils import timezone

from imperial_coldfront_plugin.models import (
    CreditTransaction,
    HX2Allocation,
    ICLProject,
    RDFAllocation,
)

from .emails import (
    Discrepancy,
    DiscrepancyCheckResult,
    QuotaDiscrepancy,
    notify_platforms_to_manually_delete_allocation,
    send_allocation_deletion_notification,
    send_allocation_deletion_warning,
    send_allocation_expiry_warning,
    send_allocation_removal_warning,
    send_discrepancy_notification,
    send_fileset_not_found_notification,
    send_hx2_access_group_discrepancy_notification,
    send_quota_discrepancy_notification,
)
from .forms import AllocationFormData
from .gid import get_new_gid
from .gpfs_client import FilesetPathInfo, GPFSClient, create_fileset_set_quota
from .ldap import ldap_create_group, ldap_delete_group, ldap_group_member_search
from .utils import get_rdf_allocation_credit_projection


def _create_rdf_allocation_debit_transaction(
    *,
    project: ICLProject,
    size_tb: int,
    start_date: date,
    end_date: date,
    description: str,
    authoriser: str,
) -> ICLProject:
    """Create a debit transaction for an RDF allocation under a project row lock."""
    locked_project = ICLProject.objects.select_for_update().get(pk=project.pk)
    current_balance, debit, projected_balance = get_rdf_allocation_credit_projection(
        project=locked_project,
        size_tb=size_tb,
        start_date=start_date,
        end_date=end_date,
    )
    if projected_balance < 0:
        raise ValueError(
            "Insufficient project credits for this allocation. "
            f"Current balance: {current_balance} credits. "
            f"Required debit: {-debit} credits."
        )

    CreditTransaction.objects.create(
        project=locked_project,
        amount=debit,
        description=description,
        authoriser=authoriser,
    )
    return locked_project


def create_rdf_allocation(form_data: AllocationFormData, authoriser: str = "") -> int:
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
    ldap_name = f"{settings.LDAP_RDF_SHORTNAME_PREFIX}{shortname}"
    should_create_credit_transaction = bool(
        settings.ENABLE_RDF_ALLOCATION_AUTO_CREDIT
        and form_data.get("create_credit_transaction", True)
    )
    credit_transaction_description = form_data.get("credit_transaction_description", "")

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

    faculty = project.faculty
    department = project.department
    group_id = project.group_id

    logger.info("Creating initial database entries for RDF allocation.")
    with transaction.atomic():
        if should_create_credit_transaction:
            project = _create_rdf_allocation_debit_transaction(
                project=project,
                size_tb=storage_size_tb,
                start_date=form_data["start_date"],
                end_date=form_data["end_date"],
                description=credit_transaction_description,
                authoriser=authoriser,
            )

        rdf_allocation = RDFAllocation.objects.create(
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

        gid = get_new_gid("rdf")
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


def find_discrepancies_helper(
    allocations: QuerySet[RDFAllocation | HX2Allocation],
    ldap_groups: dict[str, list[str]],
) -> DiscrepancyCheckResult:
    """Finds discrepancies between LDAP groups and allocation users."""
    discrepancies: list[Discrepancy] = []
    missing_ldap_groups = []
    for allocation in allocations:
        group_name = allocation.ldap_shortname

        active_users = AllocationUser.objects.filter(
            allocation=allocation, status__name="Active"
        )
        expected_usernames = [au.user.username for au in active_users]

        actual_members = ldap_groups.get(group_name)
        if actual_members is None:
            missing_ldap_groups.append(group_name)
            continue

        missing_members = set(expected_usernames) - set(actual_members)
        extra_members = set(actual_members) - set(expected_usernames)

        if missing_members or extra_members:
            discrepancies.append(
                Discrepancy(
                    group_name=group_name,
                    project_name=allocation.project.title,
                    missing_members=list(missing_members),
                    extra_members=list(extra_members),
                )
            )
    return DiscrepancyCheckResult(
        membership_discrepancies=discrepancies, missing_ldap_groups=missing_ldap_groups
    )


def check_rdf_ldap_consistency(
    send_email: bool = True,
) -> DiscrepancyCheckResult | None:
    """Check the consistency of LDAP groups with the RDF Active allocations."""
    if not settings.LDAP_ENABLED:
        return None

    allocations = RDFAllocation.objects.filter(
        resources__name="RDF Active",
        status__name="Active",
    ).distinct()
    ldap_groups = ldap_group_member_search(f"{settings.LDAP_RDF_SHORTNAME_PREFIX}*")

    check_result = find_discrepancies_helper(allocations, ldap_groups)

    if check_result.discrepancies_found and send_email:
        send_discrepancy_notification(check_result, source="RDF")

    return check_result


def check_hx2_ldap_consistency(
    send_email: bool = True,
) -> DiscrepancyCheckResult | None:
    """Check the consistency of LDAP groups with the HX2 allocations in the database."""
    if not settings.LDAP_ENABLED:
        return None

    allocations = HX2Allocation.objects.filter(
        resources__name="HX2",
        status__name="Active",
    ).distinct()
    ldap_groups = ldap_group_member_search(f"{settings.LDAP_HX2_SHORTNAME_PREFIX}*")

    check_result = find_discrepancies_helper(allocations, ldap_groups)

    if check_result.discrepancies_found and send_email:
        send_discrepancy_notification(check_result, source="HX2")

    return check_result


def update_quota_usages_task() -> None:
    """Update the usages of all quota related allocation attributes."""
    client = GPFSClient()
    usages = client.retrieve_all_fileset_quotas(settings.GPFS_FILESYSTEM_NAME)

    # use prefetch_related to reduce number of database operations
    allocations = RDFAllocation.objects.filter(
        resources__name="RDF Active"
    ).prefetch_related("allocationattribute_set")
    # below could use some more error handling but is a reasonable first pass
    for allocation in allocations:
        rdf_id = allocation.shortname
        storage_attribute_usage = (
            allocation.storage_quota_tb_attr.allocationattributeusage
        )
        storage_attribute_usage.value = round(usages[rdf_id]["block_usage_tb"], 2)
        storage_attribute_usage.save()
        files_attribute_usage = allocation.files_quota_attr.allocationattributeusage
        files_attribute_usage.value = usages[rdf_id]["files_usage"]
        files_attribute_usage.save()


def remove_ldap_group_members(usernames: list[str], group_name: str) -> None:
    """Remove members from an LDAP group.

    Args:
        usernames: The usernames to remove from the group
        group_name: The name of the LDAP group to remove members from.
    """
    from .ldap import ldap_remove_member_from_group

    # Remove each user from the LDAP group
    for username in usernames:
        ldap_remove_member_from_group(
            group_name,
            username,
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

    allocations_to_remove = RDFAllocation.objects.filter(
        # current time - end date >= remove limit
        end_date__lte=(timezone.now() - remove_limit),
        # current time - end date < delete limit
        end_date__gt=(timezone.now() - delete_limit),
        resources__name="RDF Active",
    )
    removed_status = AllocationStatusChoice.objects.get(name="Removed")
    allocations_to_remove.update(status=removed_status)

    # Delete Allocations that end beyond deletion limit
    allocations_to_delete = RDFAllocation.objects.filter(
        # current time - expiry date > expiry limit
        end_date__lte=(timezone.now() - delete_limit),
        resources__name="RDF Active",
    )
    deleted_status = AllocationStatusChoice.objects.get(name="Deleted")
    allocations_to_delete.update(status=deleted_status)

    for allocation in allocations_to_delete:
        notify_platforms_to_manually_delete_allocation(
            allocation.shortname, allocation.pk
        )


def check_rdf_allocation_expiry_notifications(send_email: bool = True) -> None:
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
    expiry_allocations = RDFAllocation.objects.filter(
        resources=rdf_resource, end_date__in=expiry_warning_dates
    ).select_related("project", "project__pi")

    for allocation in expiry_allocations:
        days_until_expiry = (allocation.end_date - today).days
        project_owner = allocation.project.pi

        logger.info(
            f"Sending expiry warning for allocation {allocation.pk} ({days_until_expiry} days)"  # noqa:E501
        )
        if send_email:
            send_allocation_expiry_warning(
                allocation.pk, project_owner.email, days_until_expiry
            )

    # Query for removal warnings
    removal_allocations = RDFAllocation.objects.filter(
        resources=rdf_resource, end_date__in=removal_warning_dates
    ).select_related("project", "project__pi")

    for allocation in removal_allocations:
        days_until_expiry = (allocation.end_date - today).days
        project_owner = allocation.project.pi

        logger.info(
            f"Sending removal warning for allocation {allocation.pk} ({days_until_expiry} days)"  # noqa:E501
        )
        if send_email:
            send_allocation_removal_warning(
                allocation.pk, project_owner.email, days_until_expiry
            )

    # Query for deletion warnings
    deletion_warning_allocations = RDFAllocation.objects.filter(
        resources=rdf_resource, end_date__in=deletion_warning_dates
    ).select_related("project", "project__pi")

    for allocation in deletion_warning_allocations:
        days_until_expiry = (allocation.end_date - today).days
        project_owner = allocation.project.pi

        logger.info(
            f"Sending deletion warning for allocation {allocation.pk} ({days_until_expiry} days)"  # noqa:E501
        )
        if send_email:
            send_allocation_deletion_warning(
                allocation.pk, project_owner.email, days_until_expiry
            )

    # Query for deletion notifications
    deletion_notification_allocations = RDFAllocation.objects.filter(
        resources=rdf_resource, end_date__in=deletion_notification_dates
    ).select_related("project", "project__pi")

    for allocation in deletion_notification_allocations:
        project_owner = allocation.project.pi

        logger.info(f"Sending deletion notification for allocation {allocation.pk}")
        if send_email:
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

    allocation = RDFAllocation.objects.get(pk=allocation_id)

    client = GPFSClient()

    try:
        shortname = allocation.shortname
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
        storage_quota_attribute = allocation.storage_quota_tb_attr
        storage_quota_attribute.value = "0"
        storage_quota_attribute.save()

        files_quota_attribute = allocation.files_quota_attr
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


def check_quota_consistency(send_email: bool = True) -> None:
    """Check consistency of file and storage quotas between allocations and filesets.

    Compares the active allocations to ensure the matching filesets have the same
    storage and file quotas. If discrepancies are found, a notification email is sent
    to admins. Also sends a notification if any allocations are found that do not have a
    matching fileset in GPFS.
    """
    if not settings.GPFS_ENABLED:
        return

    allocations = RDFAllocation.objects.filter(
        resources__name="RDF Active",
        status__name="Active",
        allocationattribute__allocation_attribute_type__name="Shortname",
    ).distinct()

    client = GPFSClient()
    usages = client.retrieve_all_fileset_quotas(settings.GPFS_FILESYSTEM_NAME)

    discrepancies: list[QuotaDiscrepancy] = []
    missing_filesets = []

    for allocation in allocations:
        shortname = allocation.shortname
        storage_attribute_quota: int = allocation.storage_quota_tb
        files_attribute_quota: int = allocation.files_quota

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

    if discrepancies and send_email:
        send_quota_discrepancy_notification(discrepancies)

    if missing_filesets and send_email:
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

    allocations = RDFAllocation.objects.filter(
        resources__name="RDF Active",
        end_date=threshold_date,  # run once when it hits the configured day
    ).prefetch_related("allocationattribute_set")

    client = GPFSClient()

    for allocation in allocations:
        try:
            shortname = allocation.shortname
        except ValueError:
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


def check_hx2_user_group_consistency(send_email: bool = True) -> Discrepancy | None:
    """Check consistency of user group memberships for HX2 allocations."""
    if not settings.LDAP_ENABLED:
        return None

    allocation_group_members = set(
        AllocationUser.objects.filter(
            status__name="Active",
            allocation__resources__name="HX2",
            allocation__status__name="Active",
        ).values_list("user__username", flat=True)
    )
    search_results = ldap_group_member_search(settings.LDAP_HX2_ACCESS_GROUP_NAME)
    try:
        ldap_group_members = set(search_results[settings.LDAP_HX2_ACCESS_GROUP_NAME])
    except KeyError:
        raise ValueError(
            "Unable to find HX2 access group in AD during consistency check."
        )

    missing_members = list(allocation_group_members - ldap_group_members)
    extra_members = list(ldap_group_members - allocation_group_members)

    if not (missing_members or extra_members):
        return None

    check_result = Discrepancy(
        group_name=settings.LDAP_HX2_ACCESS_GROUP_NAME,
        project_name="",
        missing_members=missing_members,
        extra_members=extra_members,
    )

    if send_email:
        send_hx2_access_group_discrepancy_notification(check_result)

    return check_result
