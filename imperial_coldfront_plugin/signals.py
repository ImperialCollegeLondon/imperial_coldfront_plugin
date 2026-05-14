"""Django signals.

Signals are a rather blunt instrument but are useful for hooking into models
defined by Coldfront. Here we use them to enforce some constraints on
attributes and to manage LDAP group membership.
"""

from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationUser,
)
from coldfront.core.project.models import ProjectAttribute
from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django_q.tasks import async_task

from imperial_coldfront_plugin.models import HX2Allocation, RDFAllocation

from .ldap import (
    ldap_add_member_to_group,
    ldap_gid_in_use,
    ldap_remove_member_from_group,
)
from .tasks import remove_ldap_group_members
from .utils import rdf_or_hx2_allocation


@receiver(pre_save, sender=AllocationAttribute)
def allocation_attribute_ensure_no_existing_gid(
    sender: object, instance: AllocationAttribute, **kwargs: object
) -> None:
    """Prevent saving of GID attribute if it is already in use.

    This checks both existing allocation attributes and LDAP (if enabled).

    Note that this makes all operations that create or modify GID attributes
    potentially slow as they involve a network call to the LDAP server. GID attributes
    should ideally be created in background tasks rather than in the request/response
    cycle.

    Args:
        sender: The model class.
        instance: The instance being saved.
        **kwargs: Additional keyword arguments.
    """
    if instance.allocation_attribute_type.name != "GID":
        return
    if AllocationAttribute.objects.filter(
        allocation_attribute_type__name="GID", value=instance.value
    ).exists():
        raise ValueError(
            f"GID {instance.value} is already assigned to another allocation."
        )
    if settings.LDAP_ENABLED and ldap_gid_in_use(instance.value):
        raise ValueError(f"GID {instance.value} is already in use in LDAP.")


@receiver(pre_save, sender=AllocationAttribute)
def allocation_attribute_ensure_unique_shortname(
    sender: object, instance: AllocationAttribute, **kwargs: object
) -> None:
    """Prevent saving of shortname attribute if it is not unique.

    Args:
      sender: The model class.
      instance: The instance being saved.
      **kwargs: Additional keyword arguments.
    """
    if (
        instance.allocation_attribute_type.name == "Shortname"
        and AllocationAttribute.objects.filter(
            allocation_attribute_type__name="Shortname", value=instance.value
        ).exists()
    ):
        raise ValueError(f"An allocation with {instance.value} already exists.")


@receiver(pre_save, sender=ProjectAttribute)
def project_attribute_ensure_unique_group_id(
    sender: object, instance: ProjectAttribute, **kwargs: object
) -> None:
    """Prevent saving of project group name if it is not unique.

    Args:
        sender: The model class.
        instance: The instance being saved.
        **kwargs: Additional keyword arguments.
    """
    if (
        instance.proj_attr_type.name == "Group ID"
        and ProjectAttribute.objects.filter(
            proj_attr_type__name="Group ID", value=instance.value
        ).exists()
    ):
        raise ValueError(f"A project with {instance.value} already exists.")


def _sync_membership_helper(
    allocation: RDFAllocation | HX2Allocation,
    allocation_user: AllocationUser,
    ldap_groupname: str,
) -> None:
    """Helper function to sync LDAP group membership for an AllocationUser."""
    if allocation.status.name != "Active":
        # Only manage LDAP group membership for Active allocations
        return

    if allocation_user.status.name == "Active":
        async_task(
            ldap_add_member_to_group,
            ldap_groupname,
            allocation_user.user.username,
            allow_already_present=True,
        )
    else:
        async_task(
            ldap_remove_member_from_group,
            ldap_groupname,
            allocation_user.user.username,
            allow_missing=True,
        )


@receiver(post_save, sender=AllocationUser)
def allocation_user_sync_ldap_group_membership(
    sender: object, instance: AllocationUser, **kwargs: object
) -> None:
    """Add or remove members from an ldap group based on AllocationUser.status.

    Note this signal invokes a background task to do the actual LDAP operation. This
    leaves the potential for the database and LDAP to get out of sync if the task
    fails, but avoids making the request/response cycle slow.

    Args:
        sender: The model class.
        instance: The instance being saved.
        **kwargs: Additional keyword arguments.
    """
    if not settings.LDAP_ENABLED:
        return

    try:
        allocation = rdf_or_hx2_allocation(instance.allocation)
    except ValueError:
        # Instantiating a RDFAllocation checks it's actually a RDFAllocation
        return

    _sync_membership_helper(allocation, instance, allocation.ldap_shortname)


def _delete_ldap_group_membership_helper(
    allocation: RDFAllocation | HX2Allocation,
    user: AllocationUser,
    ldap_groupname: str,
) -> None:
    """Helper function to remove LDAP group membership for an AllocationUser."""
    if allocation.status.name != "Active":
        # Only manage LDAP group membership for Active allocations
        return

    async_task(
        ldap_remove_member_from_group,
        ldap_groupname,
        user.user.username,
        allow_missing=True,
    )


@receiver(post_delete, sender=AllocationUser)
def allocation_user_ldap_group_membership_deletion(
    sender: object, instance: AllocationUser, **kwargs: object
) -> None:
    """Remove an ldap group member if the associated AllocationUser is deleted.

    This isn't expected to come up in the usual course of things as removing a user via
    the UI does not delete the AllocationUser object. Just covering it for completeness.

    Note this signal invokes a background task to do the actual LDAP operation. This
    leaves the potential for the database and LDAP to get out of sync if the task
    fails, but avoids making the request/response cycle slow.

    Args:
        sender: The model class.
        instance: The instance being deleted.
        **kwargs: Additional keyword arguments.
    """
    if not settings.LDAP_ENABLED:
        return

    try:
        allocation = rdf_or_hx2_allocation(instance.allocation)
    except ValueError:
        # Instantiating a RDFAllocation checks it's actually a RDFAllocation
        return

    _delete_ldap_group_membership_helper(
        allocation, instance, allocation.ldap_shortname
    )


@receiver(post_save, sender=AllocationUser)
def allocation_user_sync_hx2_access_group(
    sender: object,
    instance: AllocationUser,
    **kwargs: object,
) -> None:
    """Add or remove members from the HX2 access group based on allocation status."""
    if not settings.LDAP_ENABLED:
        return

    try:
        allocation = HX2Allocation.from_allocation(instance.allocation)
    except ValueError:
        # Signal applies only to HX2Allocations
        return

    _sync_membership_helper(allocation, instance, settings.LDAP_HX2_ACCESS_GROUP_NAME)


@receiver(post_delete, sender=AllocationUser)
def allocation_user_hx2_access_group_deletion(
    sender: object,
    instance: AllocationUser,
    **kwargs: object,
) -> None:
    """Remove a user from the HX2 access group if the AllocationUser is deleted.

    This isn't expected to come up in the usual course of things as removing a user via
    the UI does not delete the AllocationUser object. Just covering it for completeness.
    """
    if not settings.LDAP_ENABLED:
        return

    try:
        allocation = HX2Allocation.from_allocation(instance.allocation)
    except ValueError:
        # Signal applies only to HX2Allocations
        return

    _delete_ldap_group_membership_helper(
        allocation, instance, settings.LDAP_HX2_ACCESS_GROUP_NAME
    )


def _remove_ldap_group_members_if_inactive_helper(
    allocation: RDFAllocation | HX2Allocation,
    group_name: str,
) -> None:
    """Helper function to remove all LDAP group members if allocation is not Active."""
    if allocation.status.name == "Active":
        return

    usernames = allocation.allocationuser_set.filter(status__name="Active").values_list(
        "user__username", flat=True
    )

    async_task(remove_ldap_group_members, list(usernames), group_name)


@receiver(post_save, sender=Allocation)
@receiver(post_save, sender=RDFAllocation)
@receiver(post_save, sender=HX2Allocation)
def allocation_remove_ldap_group_members_if_inactive(
    sender: object,
    instance: Allocation | RDFAllocation | HX2Allocation,
    **kwargs: object,
) -> None:
    """Remove all LDAP group members if allocation is not Active.

    The LDAP group itself is not deleted.
    """
    if not settings.LDAP_ENABLED:
        return
    try:
        allocation = rdf_or_hx2_allocation(instance)
    except ValueError:
        return

    if (
        isinstance(allocation, RDFAllocation)
        and not settings.ENABLE_RDF_ALLOCATION_LIFECYCLE
    ):
        return

    _remove_ldap_group_members_if_inactive_helper(allocation, allocation.ldap_shortname)


@receiver(post_save, sender=Allocation)
@receiver(post_save, sender=HX2Allocation)
def allocation_remove_hx2_access_group_if_inactive(
    sender: object,
    instance: Allocation | HX2Allocation,
    **kwargs: object,
) -> None:
    """Remove all members from the HX2 access group if allocation is not Active."""
    if not settings.LDAP_ENABLED:
        return
    try:
        allocation = HX2Allocation.from_allocation(instance)
    except ValueError:
        # Signal applies only to HX2Allocations
        return

    _remove_ldap_group_members_if_inactive_helper(
        allocation, settings.LDAP_HX2_ACCESS_GROUP_NAME
    )


@receiver(pre_save, sender=RDFAllocation)
@receiver(pre_save, sender=Allocation)
def allocation_expiry_zero_quota(
    sender: type[RDFAllocation],
    instance: Allocation | RDFAllocation,
    **kwargs: object,
) -> None:
    """Spawn a background task to zero GPFS quota when an RDF Active allocation has expired."""  # noqa E501
    if instance.pk is None:
        return

    if instance.status.name != "Expired":
        return

    try:
        RDFAllocation.from_allocation(instance)
    except ValueError:
        return

    try:
        old_instance = RDFAllocation.objects.get(pk=instance.pk)
    except RDFAllocation.DoesNotExist:
        return

    if old_instance.status.name != "Active":
        return

    async_task(
        "imperial_coldfront_plugin.tasks.zero_allocation_gpfs_quota",
        instance.pk,
    )


@receiver(pre_save, sender=Allocation)
@receiver(pre_save, sender=HX2Allocation)
def allocation_prevent_multiple_hx2_allocations_per_project(
    sender: type[HX2Allocation],
    instance: HX2Allocation | Allocation,
    **kwargs: object,
) -> None:
    """Prevent saving HX2Allocation if the project already has an HX2Allocation."""
    existing_allocations = HX2Allocation.objects.filter(
        project=instance.project,
        resources__name="HX2",
    )

    if instance.pk is not None:
        existing_allocations = existing_allocations.exclude(pk=instance.pk)

    if existing_allocations.exists():
        raise ValueError(f"Project {instance.project} already has an HX2 allocation.")


@receiver(pre_save, sender=AllocationUser)
def allocation_user_prevent_multiple_hx2(
    sender: type[AllocationUser],
    instance: AllocationUser,
    **kwargs: object,
) -> None:
    """Prevent an AllocationUser from being active on multiple HX2 allocations."""
    if instance.status.name != "Active":
        return

    try:
        HX2Allocation.from_allocation(instance.allocation)
    except ValueError:
        # Signal applies only to HX2Allocations
        return

    active_hx2_allocations = AllocationUser.objects.filter(
        user=instance.user,
        status__name="Active",
        allocation__resources__name="HX2",
        allocation__status__name="Active",
    ).exclude(pk=instance.pk)

    if active_hx2_allocations.exists():
        raise ValueError(
            f"User {instance.user.username} is already active on a HX2 allocation."
        )
