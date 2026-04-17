"""Template tags relating to projects."""

from typing import TYPE_CHECKING

from coldfront.core.project.models import ProjectUser
from django import template
from django.db.models.query import QuerySet

from imperial_coldfront_plugin.microsoft_graph_client import get_graph_api_client
from imperial_coldfront_plugin.models import ICLProject
from imperial_coldfront_plugin.policy import user_eligible_to_be_pi
from imperial_coldfront_plugin.utils import calculate_credit_balance

if TYPE_CHECKING:
    from django.contrib.auth.models import User

register = template.Library()


@register.simple_tag
def get_user_project_memberships(user: "User") -> QuerySet[ICLProject]:
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
def get_user_owned_projects(user: "User") -> QuerySet[ICLProject]:
    """Return a queryset with a user's owned projects.

    Args:
      user: The user whose owned projects are to be retrieved.

    Returns:
        A queryset of the user's active owned projects.
    """
    return ICLProject.objects.filter(pi=user, status__name="Active")


@register.simple_tag
def user_owns_projects(user: "User") -> bool:
    """Return whether a user owns any projects.

    Args:
      user: The user to check.

    Returns:
        True if the user owns at least one active project.
    """
    return get_user_owned_projects(user).exists()


@register.simple_tag
def user_can_self_create_project(user: "User") -> bool:
    """Return whether a user is eligible to self-create a project.

    Args:
      user: The user to check.

    Returns:
        True if the user passes the PI eligibility policy.
    """
    user_profile = get_graph_api_client().user_profile(user.username)
    return user_eligible_to_be_pi(user_profile)


@register.simple_tag
def get_project_credit_balance(project: ICLProject) -> int:
    """Calculate the total credit balance for a project.

    Args:
      project: The project whose credit balance is to be calculated.

    Returns:
        The total credit balance (sum of all transaction amounts).
    """
    balance = calculate_credit_balance(project)
    return balance if balance is not None else 0
