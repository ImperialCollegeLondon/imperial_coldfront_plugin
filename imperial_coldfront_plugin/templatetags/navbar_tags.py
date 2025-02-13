"""Template tags for the navbar."""

from django import template
from django.urls import reverse

from ..models import GroupMembership, ResearchGroup

register = template.Library()


@register.simple_tag
def get_group_url(user):
    """Get the URL for a group owned or managed by user."""
    try:
        group = ResearchGroup.objects.get(owner=user)
    except ResearchGroup.DoesNotExist:
        try:
            group = GroupMembership.objects.get(member=user, is_manager=True).group
        except GroupMembership.DoesNotExist:
            return None
    return reverse("imperial_coldfront_plugin:group_members", args=[group.pk])
