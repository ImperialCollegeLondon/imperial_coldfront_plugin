"""Plugin tasks."""

import functools
import logging
from collections.abc import Callable
from datetime import timedelta

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

from .emails import Discrepancy, send_discrepancy_notification
from .forms import AllocationFormData
from .gid import get_new_gid
from .gpfs_client import FilesetPathInfo, GPFSClient, create_fileset_set_quota
from .ldap import ldap_create_group, ldap_delete_group, ldap_group_member_search


class log_task_exceptions_to_django_logger:
    """Decorator to log exceptions raised in a background task to the django logger.

    This is useful when using django-q as the task runner, as exceptions raised in tasks
    will not trigger email notifications to admins. In production, the django logger
    will send emails on errors. This decorator ensures this happens on task failures.
    """

    def __init__(self, func: Callable[..., object]) -> None:  # type: ignore[misc]
        """Initialize the decorator with the function to wrap.

        Args:
            func: The function to wrap.
        """
        self.func = func
        self.logger = logging.getLogger("django")
        functools.update_wrapper(self, func)

    def __call__(self, *args: object, **kwargs: object) -> object:
        """Call the wrapped function, logging any exceptions raised."""
        try:
            return self.func(*args, **kwargs)
        except Exception:
            self.logger.exception("Error during background task")
            raise


def _create_rdf_allocation(form_data: AllocationFormData) -> int:
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


def _check_ldap_consistency() -> list[Discrepancy]:
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


def _update_quota_usages_task() -> None:
    """Update the usages of all quota related allocation attributes."""
    client = GPFSClient()
    usages = client.retrieve_all_fileset_usages(settings.GPFS_FILESYSTEM_NAME)

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


def _remove_allocation_group_members(allocation_id: int) -> None:
    """Background task: remove all active members from an LDAP group.

    Args:
        allocation_id: The primary key of the allocation.
    """
    from .ldap import ldap_remove_member_from_group

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


def _change_expired_allocations_to_deleted() -> None:
    """Change the status of allocations when X days past expiry to "Deleted"."""
    expiry_limit = timedelta(days=settings.RDF_ALLOCATION_EXPIRY_DELETION_DAYS)
    expired_allocations = Allocation.objects.filter(
        # Change delete status when current time - expiry date > expiry limit
        end_date__lt=(timezone.now() - expiry_limit),
    )
    deleted_status = AllocationStatusChoice.objects.get(name="Deleted")
    expired_allocations.update(status=deleted_status)


remove_allocation_group_members = log_task_exceptions_to_django_logger(
    _remove_allocation_group_members
)

# note that we can't use log_task_exceptions_to_django_logger as a decorator
# here as django-q needs to be able to serialize the function for use as a task
create_rdf_allocation = log_task_exceptions_to_django_logger(_create_rdf_allocation)
check_ldap_consistency = log_task_exceptions_to_django_logger(_check_ldap_consistency)
update_quota_usages_task = log_task_exceptions_to_django_logger(
    _update_quota_usages_task
)
change_expired_allocations_to_deleted = log_task_exceptions_to_django_logger(
    _change_expired_allocations_to_deleted
)
