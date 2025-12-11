"""Utility functions for the Imperial Coldfront plugin."""

from coldfront.core.allocation.models import Allocation, AllocationAttribute
from coldfront.core.project.models import Project
from django.db.models import Sum

from imperial_coldfront_plugin.models import CreditTransaction


def get_allocation_shortname(allocation: Allocation) -> str:
    """Get the shortname attribute for an allocation.

    Args:
      allocation: The allocation whose shortname is to be retrieved.

    Returns:
        The shortname of the allocation, or an empty string if unable
    """
    try:
        return allocation.allocationattribute_set.get(
            allocation_attribute_type__name="Shortname"
        ).value
    except (
        AllocationAttribute.MultipleObjectsReturned,
        AllocationAttribute.DoesNotExist,
    ):
        return ""


def calculate_credit_balance(project: Project) -> int:
    """Return the summed credit balance for a project.

    Args:
        project: The project whose credit balance is to be calculated.

    Returns:
        The total credit balance as an integer, or None if there are no transactions.
    """
    result = CreditTransaction.objects.filter(project=project).aggregate(
        total=Sum("amount")
    )["total"]
    return result
