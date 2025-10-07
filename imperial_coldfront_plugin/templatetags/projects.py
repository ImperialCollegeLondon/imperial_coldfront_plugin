"""Template tags relating to projects."""

from typing import TYPE_CHECKING

from coldfront.core.project.models import ProjectUser
from django import template

if TYPE_CHECKING:
    from django.contrib.auth.models import User

register = template.Library()


@register.simple_tag
def get_user_projects(user: "User") -> str:
    """Return a queryset with a user's projects."""
    return ProjectUser.objects.filter(user=user, status__name="Active").values(
        "project"
    )
