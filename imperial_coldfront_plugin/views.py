"""Plugin views."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def add_to_group(request: HttpRequest) -> HttpResponse:
    """Add an individual to a group."""
    return render(
        request=request, template_name="imperial_coldfront_plugin/add_to_group.html"
    )


def add_to_group_confirm(request: HttpRequest) -> HttpResponse:
    """Confirm adding an individual to a group."""
    return render(
        request=request,
        template_name="imperial_coldfront_plugin/add_to_group_confirm.html",
    )
