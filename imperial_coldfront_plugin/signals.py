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

from .ldap import (
    ldap_add_member_to_group,
    ldap_gid_in_use,
    ldap_remove_member_from_group,
)


def _get_shortname_from_allocation(allocation: Allocation) -> str | None:
    try:
        shortname = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Shortname"
        ).value
        return f"{settings.LDAP_SHORTNAME_PREFIX}{shortname}"
    except AllocationAttribute.MultipleObjectsReturned:
        raise ValueError(f"Multiple shortnames found for allocation - {allocation}")
    except AllocationAttribute.DoesNotExist:
        return None


@receiver(pre_save, sender=AllocationAttribute)
def ensure_no_existing_gid(
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
    ):
        raise ValueError(
            f"GID {instance.value} is already assigned to another allocation."
        )
    if settings.LDAP_ENABLED and ldap_gid_in_use(instance.value):
        raise ValueError(f"GID {instance.value} is already in use in LDAP.")


@receiver(pre_save, sender=AllocationAttribute)
def ensure_unique_shortname(
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
        )
    ):
        raise ValueError(f"An allocation with {instance.value} already exists.")


@receiver(pre_save, sender=ProjectAttribute)
def ensure_unique_group_id(
    sender: object, instance: ProjectAttribute, **kwargs: object
) -> None:
    """Prevent saving of project group name if it is not unique.

    Args:
        sender: The model class.
        instance: The instance being saved.
        **kwargs: Additional keyword arguments.
    """
    if instance.proj_attr_type.name == "Group ID" and ProjectAttribute.objects.filter(
        proj_attr_type__name="Group ID", value=instance.value
    ):
        raise ValueError(f"A project with {instance.value} already exists.")


@receiver(post_save, sender=AllocationUser)
def sync_ldap_group_membership(
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

    if (group_id := _get_shortname_from_allocation(instance.allocation)) is None:
        return

    if instance.status.name == "Active":
        async_task(
            ldap_add_member_to_group,
            group_id,
            instance.user.username,
            allow_already_present=True,
        )
    else:
        async_task(
            ldap_remove_member_from_group,
            group_id,
            instance.user.username,
            allow_missing=True,
        )


@receiver(post_delete, sender=AllocationUser)
def remove_ldap_group_membership(
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

    if (group_id := _get_shortname_from_allocation(instance.allocation)) is None:
        return

    async_task(
        ldap_remove_member_from_group,
        group_id,
        instance.user.username,
        allow_missing=True,
    )


@receiver(post_save, sender=Allocation)
def remove_ldap_group_members_if_allocation_inactive(
    sender: object, instance: Allocation, **kwargs: object
) -> None:
    """Remove all LDAP group members if allocation is not Active.

    The LDAP group itself is not deleted.
    """
    from .tasks import remove_allocation_group_members

    if not settings.LDAP_ENABLED:
        return

    if instance.status.name == "Active":
        return

    if _get_shortname_from_allocation(instance) is None:
        return

    async_task(remove_allocation_group_members, instance.pk)


"""Signal handlers for the imperial_coldfront_plugin."""


@receiver(pre_save, sender=Allocation)
def allocation_expired_handler(sender, instance, **kwargs):
    """Spawn a background task to zero GPFS quota when an allocation has expired."""
    if instance.pk is None:
        return

    if instance.status.name != "Expired":
        return

    try:
        old_instance = Allocation.objects.get(pk=instance.pk)
    except Allocation.DoesNotExist:
        return

    if old_instance.status == instance.status:
        return

    async_task(
        "imperial_coldfront_plugin.tasks.zero_allocation_gpfs_quota",
        instance.pk,
    )
