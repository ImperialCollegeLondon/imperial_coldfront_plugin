"""Utility functions for the Imperial Coldfront plugin."""

from datetime import date, timedelta
from math import ceil

import pint
from coldfront.core.allocation.models import Allocation, AllocationAttribute
from django.conf import settings
from django.db.models import Sum

from imperial_coldfront_plugin.models import (
    CreditTransaction,
    HXAllocation,
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


def calculate_rdf_allocation_credit_debit(size_tb: int, months: int) -> int:
    """Calculate the debit amount for a proposed RDF allocation.

    Debits are represented as negative values.

    Args:
        size_tb: The requested storage size in terabytes.
        months: The number of months the allocation will run for.

    Returns:
        The debit amount as a negative integer.
    """
    charging_rate = settings.SERVICE_CHARGING_RATES["rdf_active"]
    size = size_tb * pint.Unit("terabyte")
    duration = months * pint.Unit("month")
    charge = (charging_rate * size * duration).to("dimensionless")
    return -ceil(charge.magnitude)


def calculate_rdf_allocation_end_date(start_date: date, months: int) -> date:
    """Calculate the inclusive end date of an RDF allocation.

    Months are converted to days using pint's definition of a month, rounded to the
    nearest whole day.

    Args:
        start_date: Allocation start date.
        months: The number of months the allocation will run for.

    Returns:
        The last day of the allocation.
    """
    days = round((months * pint.Unit("month")).to("day").magnitude)
    return start_date + timedelta(days=days - 1)


def get_rdf_allocation_credit_projection(
    project: ICLProject,
    size_tb: int,
    months: int,
) -> tuple[int, int, int]:
    """Return current balance, debit and projected balance for an RDF allocation.

    Args:
        project: Project to evaluate.
        size_tb: Requested storage size in terabytes.
        months: The number of months the allocation will run for.

    Returns:
        Tuple of current_balance, debit, projected_balance.
    """
    current_balance = calculate_credit_balance(project)
    debit = calculate_rdf_allocation_credit_debit(size_tb=size_tb, months=months)
    return current_balance, debit, current_balance + debit


def rdf_or_hx_allocation(instance: Allocation) -> RDFAllocation | HXAllocation:
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
        return HXAllocation.from_allocation(instance)
