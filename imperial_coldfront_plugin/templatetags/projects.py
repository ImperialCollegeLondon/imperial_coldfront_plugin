"""Template tags relating to projects."""

from typing import TYPE_CHECKING

from coldfront.core.project.models import Project, ProjectUser
from django import template
from django.db.models import Sum
from django.db.models.query import QuerySet

if TYPE_CHECKING:
    from django.contrib.auth.models import User

register = template.Library()


@register.simple_tag
def get_user_projects(user: "User") -> QuerySet[Project]:
    """Return a queryset with a user's projects.

    Args:
      user: The user whose projects are to be retrieved.

    Returns:
        A queryset of the user's active projects.
    """
    return ProjectUser.objects.filter(user=user, status__name="Active").values(
        "project"
    )


@register.simple_tag
def get_project_credit_balance(project: Project) -> int:
    """Calculate the total credit balance for a project.

    Args:
      project: The project whose credit balance is to be calculated.

    Returns:
        The total credit balance (sum of all transaction amounts).
    """
    from imperial_coldfront_plugin.models import CreditTransaction

    balance = CreditTransaction.objects.filter(project=project).aggregate(
        total=Sum("amount")
    )["total"]
    return balance if balance is not None else 0
