"""Utility functions for the Imperial Coldfront plugin."""

from datetime import date
from math import ceil

import pint
from coldfront.core.allocation.models import Allocation, AllocationAttribute
from django.conf import settings
from django.db.models import Sum

from imperial_coldfront_plugin.models import (
    CreditTransaction,
    HX2Allocation,
    ICLProject,
    RDFAllocation,
)


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


def calculate_credit_balance(project: ICLProject) -> int:
    """Return the summed credit balance for a project.

    Args:
        project: The project whose credit balance is to be calculated.

    Returns:
        The total credit balance as an integer. Returns 0 if the project has no
        credit transactions.
    """
    result = CreditTransaction.objects.filter(project=project).aggregate(
        total=Sum("amount")
    )["total"]
    return result or 0


def calculate_rdf_allocation_credit_debit(
    size_tb: int,
    start_date: date,
    end_date: date,
) -> int:
    """Calculate the debit amount for a proposed RDF allocation.

    Debits are represented as negative values.

    Args:
        size_tb: The requested storage size in terabytes.
        start_date: Allocation start date.
        end_date: Allocation end date.

    Returns:
        The debit amount as a negative integer.

    Raises:
        ValueError: If end_date precedes start_date.
    """
    if end_date < start_date:
        raise ValueError("End date must be on or after start date.")

    duration_days = (end_date - start_date).days + 1
    charging_rate = settings.SERVICE_CHARGING_RATES["rdf_active"]
    size = size_tb * pint.Unit("terabyte")
    duration = duration_days * pint.Unit("day")
    charge = (charging_rate * size * duration).to("dimensionless")
    return -ceil(charge.magnitude)


def get_rdf_allocation_credit_projection(
    project: ICLProject,
    size_tb: int,
    start_date: date,
    end_date: date,
) -> tuple[int, int, int]:
    """Return current balance, debit and projected balance for an RDF allocation.

    Args:
        project: Project to evaluate.
        size_tb: Requested storage size in terabytes.
        start_date: Allocation start date.
        end_date: Allocation end date.

    Returns:
        Tuple of current_balance, debit, projected_balance.
    """
    current_balance = calculate_credit_balance(project)
    debit = calculate_rdf_allocation_credit_debit(
        size_tb=size_tb,
        start_date=start_date,
        end_date=end_date,
    )
    return current_balance, debit, current_balance + debit


def rdf_or_hx2_allocation(instance: Allocation) -> RDFAllocation | HX2Allocation:
    """Attempt to instantiate RDFAllocation or HX2Allocation from the given Allocation.

    Raises a ValueError if unable to do either.

    Args:
        instance: The Allocation instance to convert.

    Returns:
        An instance of RDFAllocation or HX2Allocation from the given Allocation.
    """
    try:
        return RDFAllocation.from_allocation(instance)
    except ValueError:
        return HX2Allocation.from_allocation(instance)
