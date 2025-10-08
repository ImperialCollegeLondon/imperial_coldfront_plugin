"""Template tags for allocation shortnames."""

from coldfront.core.allocation.models import Allocation
from django import template

from ..utils import get_allocation_shortname

register = template.Library()


@register.simple_tag
def allocation_shortname(allocation: Allocation) -> str:
    """Render the shortname of an allocation.

    Args:
      allocation: The allocation whose shortname is to be retrieved.

    Returns:
      The shortname of the allocation, or an empty string if unable.
    """
    return get_allocation_shortname(allocation)
