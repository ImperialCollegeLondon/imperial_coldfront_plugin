"""Template tags relating to projects."""

from typing import TYPE_CHECKING

from coldfront.core.project.models import Project, ProjectUser
from django import template
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
