"""Template tags for allocation shortnames."""

from coldfront.core.allocation.models import Allocation
from django import template

from ..utils import get_allocation_shortname

register = template.Library()


@register.simple_tag
def allocation_shortname(allocation: Allocation) -> str:
    """Render the shortname of an allocation."""
    return get_allocation_shortname(allocation)
