from datetime import date

import pytest

from imperial_coldfront_plugin.models import CreditTransaction
from imperial_coldfront_plugin.utils import (
    calculate_credit_balance,
    calculate_rdf_allocation_credit_debit,
    calculate_rdf_allocation_end_date,
    get_rdf_allocation_credit_projection,
)


@pytest.mark.django_db
def test_calculate_credit_balance_returns_sum(project):
    """Test that calculate_credit_balance returns the correct sum."""
    CreditTransaction.objects.create(project=project, amount=50, description="initial")
    CreditTransaction.objects.create(project=project, amount=10, description="refund")
    CreditTransaction.objects.create(project=project, amount=25, description="bonus")

    assert calculate_credit_balance(project) == 85


def test_calculate_rdf_allocation_credit_debit_per_month():
    """Test debit is months x monthly rate x terabytes."""
    assert calculate_rdf_allocation_credit_debit(size_tb=1, months=1) == -5
    assert calculate_rdf_allocation_credit_debit(size_tb=2, months=12) == -120


def test_calculate_rdf_allocation_end_date_for_year():
    """Test twelve months ends 364 days after the start date."""
    assert calculate_rdf_allocation_end_date(date(2026, 1, 1), 12) == date(2026, 12, 31)


def test_calculate_rdf_allocation_end_date_single_month():
    """Test one month (30.4375 days, rounded) is inclusive of the start date."""
    assert calculate_rdf_allocation_end_date(date(2026, 1, 1), 1) == date(2026, 1, 30)


def test_calculate_rdf_allocation_end_date_short_month():
    """Test months shorter than 30.4375 days and overflow into the next month."""
    assert calculate_rdf_allocation_end_date(date(2026, 2, 1), 1) == date(2026, 3, 2)


@pytest.mark.django_db
def test_get_rdf_allocation_credit_projection(project):
    """Test projection returns expected current balance, debit and projected balance."""
    CreditTransaction.objects.create(project=project, amount=150, description="credit")

    current_balance, debit, projected_balance = get_rdf_allocation_credit_projection(
        project=project,
        size_tb=2,
        months=12,
    )

    assert current_balance == 150
    assert debit == -120
    assert projected_balance == 30
