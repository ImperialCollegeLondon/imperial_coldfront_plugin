from datetime import date

import pytest

from imperial_coldfront_plugin.models import CreditTransaction
from imperial_coldfront_plugin.utils import (
    calculate_credit_balance,
    calculate_rdf_allocation_credit_debit,
    get_rdf_allocation_credit_projection,
)


@pytest.mark.django_db
def test_calculate_credit_balance_returns_sum(project):
    """Test that calculate_credit_balance returns the correct sum."""
    CreditTransaction.objects.create(project=project, amount=50, description="initial")
    CreditTransaction.objects.create(project=project, amount=10, description="refund")
    CreditTransaction.objects.create(project=project, amount=25, description="bonus")

    assert calculate_credit_balance(project) == 85


def test_calculate_rdf_allocation_credit_debit_uses_inclusive_days():
    """Test debit calculation uses inclusive day count and rounding."""
    debit = calculate_rdf_allocation_credit_debit(
        size_tb=1, start_date=date(2026, 1, 1), end_date=date(2026, 2, 1)
    )

    assert debit == -5


def test_calculate_rdf_allocation_credit_debit_for_full_year():
    """Test debit calculation for a one-year allocation period."""
    debit = calculate_rdf_allocation_credit_debit(
        size_tb=2,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )

    assert debit == -100


def test_calculate_rdf_allocation_credit_debit_invalid_date_range():
    """Test debit calculation rejects end dates before start dates."""
    with pytest.raises(ValueError, match="End date must be on or after start date"):
        calculate_rdf_allocation_credit_debit(
            size_tb=1,
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 1),
        )


@pytest.mark.django_db
def test_get_rdf_allocation_credit_projection(project):
    """Test projection returns expected current balance, debit and projected balance."""
    CreditTransaction.objects.create(project=project, amount=120, description="credit")

    current_balance, debit, projected_balance = get_rdf_allocation_credit_projection(
        project=project,
        size_tb=2,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )

    assert current_balance == 120
    assert debit == -100
    assert projected_balance == 20
