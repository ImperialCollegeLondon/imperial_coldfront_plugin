"""Template tags for the home view."""

from django import template

from ..microsoft_graph_client import get_graph_api_client
from ..models import GroupMembership, ResearchGroup
from ..policy import user_eligible_to_be_pi

register = template.Library()


@register.simple_tag
def owns_a_group(user):
    """Check if the user owns a ResearchGroup."""
    return ResearchGroup.objects.filter(owner=user).exists()


@register.simple_tag
def is_a_group_member(user):
    """Check if the user is a member of a ResearchGroup."""
    return GroupMembership.objects.filter(member=user).exists()


@register.simple_tag
def is_eligible_to_own_a_group(user):
    """Check if the user is eligible to own a group."""
    client = get_graph_api_client()
    user_profile = client.user_profile(user.username)
    return user_eligible_to_be_pi(user_profile)
