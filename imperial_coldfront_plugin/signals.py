"""Django signals."""

from coldfront.core.allocation.models import AllocationAttribute, AllocationUser
from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .ldap import (
    ldap_add_member_to_group_in_background,
    ldap_remove_member_from_group_in_background,
)


def _get_group_id_from_allocation(allocation):
    try:
        return allocation.allocationattribute_set.get(
            allocation_attribute_type__name="RDF Project ID"
        ).value
    except AllocationAttribute.MultipleObjectsReturned:
        raise ValueError(
            f"Multiple RDF project ids found for allocation - {allocation}"
        )
    except AllocationAttribute.DoesNotExist:
        return


@receiver(post_save, sender=AllocationUser)
def sync_ldap_group_membership(sender, instance, **kwargs):
    """Add or remove members from an ldap group based on AllocationUser.status."""
    if not settings.LDAP_ENABLED:
        return

    if (group_id := _get_group_id_from_allocation(instance.allocation)) is None:
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

    if (group_id := _get_group_id_from_allocation(instance.allocation)) is None:
        return

    ldap_remove_member_from_group_in_background(
        group_id, instance.user.username, allow_missing=True
    )
