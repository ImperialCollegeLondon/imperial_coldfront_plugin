"""Utility functions for the Imperial Coldfront plugin."""

from django.db.models import Sum

from imperial_coldfront_plugin.models import CreditTransaction, RDFProject


def calculate_credit_balance(project: RDFProject) -> int:
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
