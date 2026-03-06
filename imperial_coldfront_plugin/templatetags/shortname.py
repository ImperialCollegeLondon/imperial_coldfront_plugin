"""Template tags for allocation shortnames."""

from django import template

from imperial_coldfront_plugin.models import RDFAllocation

register = template.Library()


@register.simple_tag
def allocation_shortname(allocation: RDFAllocation) -> str:
    """Render the shortname of an allocation.

    Args:
      allocation: The allocation whose shortname is to be retrieved.

    Returns:
      The shortname of the allocation, or an empty string if unable.
    """
    return allocation.shortname
