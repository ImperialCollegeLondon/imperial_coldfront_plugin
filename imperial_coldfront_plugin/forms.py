"""Forms for the Imperial Coldfront plugin.

This module contains form classes used for Research Group creation.
"""

from django import forms


class ResearchGroupForm(forms.Form):
    """Form with terms acceptance checkbox and group name input."""

    name = forms.CharField(max_length=255, label="Research Group name", required=True)
    accept_terms = forms.BooleanField(
        required=True, label="I accept the terms and conditions"
    )
