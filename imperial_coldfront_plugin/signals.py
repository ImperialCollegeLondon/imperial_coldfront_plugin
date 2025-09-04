"""Django signals."""

from coldfront.core.allocation.models import AllocationAttribute, AllocationUser
from coldfront.core.project.models import ProjectAttribute
from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .ldap import (
    ldap_add_member_to_group_in_background,
    ldap_remove_member_from_group_in_background,
)


def _get_shortname_from_allocation(allocation):
    try:
        shortname = allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Shortname"
        ).value
        return f"{settings.LDAP_SHORTNAME_PREFIX}{shortname}"
    except AllocationAttribute.MultipleObjectsReturned:
        raise ValueError(f"Multiple shortnames found for allocation - {allocation}")
    except AllocationAttribute.DoesNotExist:
        return


@receiver(pre_save, sender=AllocationAttribute)
def ensure_unique_shortname(sender, instance, **kwargs):
    """Prevent saving of shortname attribute if it is not unique."""
    if (
        instance.allocation_attribute_type.name == "Shortname"
        and AllocationAttribute.objects.filter(
            allocation_attribute_type__name="Shortname", value=instance.value
        )
    ):
        raise ValueError(f"An allocation with {instance.value} already exists.")


@receiver(pre_save, sender=ProjectAttribute)
def ensure_unique_group_id(sender, instance, **kwargs):
    """Prevent saving of project group name if it is not unique."""
    if instance.proj_attr_type.name == "Group ID" and ProjectAttribute.objects.filter(
        proj_attr_type__name="Group ID", value=instance.value
    ):
        raise ValueError(f"A project with {instance.value} already exists.")


@receiver(post_save, sender=AllocationUser)
def sync_ldap_group_membership(sender, instance, **kwargs):
    """Add or remove members from an ldap group based on AllocationUser.status."""
    if not settings.LDAP_ENABLED:
        return

    if (group_id := _get_shortname_from_allocation(instance.allocation)) is None:
        return

    if instance.status.name == "Active":
        ldap_add_member_to_group_in_background(
            group_id, instance.user.username, allow_already_present=True
        )
    else:
        ldap_remove_member_from_group_in_background(
            group_id, instance.user.username, allow_missing=True
        )


@receiver(post_delete, sender=AllocationUser)
def remove_ldap_group_membership(sender, instance, **kwargs):
    """Remove an ldap group member if the associated AllocationUser is deleted.

    This isn't expected to come up in the usual course of things as removing a user via
    the UI does not delete the AllocationUser object. Just cover it for completeness.
    """
    if not settings.LDAP_ENABLED:
        return

    if (group_id := _get_shortname_from_allocation(instance.allocation)) is None:
        return

    ldap_remove_member_from_group_in_background(
        group_id, instance.user.username, allow_missing=True
    )
