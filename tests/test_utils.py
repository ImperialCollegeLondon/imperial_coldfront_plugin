import pytest

from imperial_coldfront_plugin.models import CreditTransaction
from imperial_coldfront_plugin.utils import calculate_credit_balance


@pytest.mark.django_db
def test_calculate_credit_balance_returns_sum(project):
    """Test that calculate_credit_balance returns the correct sum."""
    CreditTransaction.objects.create(project=project, amount=50, description="initial")
    CreditTransaction.objects.create(project=project, amount=10, description="refund")
    CreditTransaction.objects.create(project=project, amount=25, description="bonus")

    assert calculate_credit_balance(project) == 85
