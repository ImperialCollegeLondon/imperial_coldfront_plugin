"""Forms for the Imperial Coldfront plugin.

This module contains form classes used for research group management.
"""

from django import forms


class GroupMembershipForm(forms.Form):
    """Form for inviting a user to a research group."""

    username = forms.CharField()
    expiration = forms.DateField()


class TermsAndConditionsForm(forms.Form):
    """Form for accepting terms and conditions."""

    accept = forms.BooleanField(
        label="I accept the terms and conditions",
        required=True,
        error_messages={"required": "You must accept the terms and conditions"},
    )


class UserSearchForm(forms.Form):
    """Form for searching users."""

    search = forms.CharField(
        label="Search",
        help_text="Provide the name or username of the user to look for. "
        "The search is not case sensitive",
        required=True,
        error_messages={"required": "You must include a search term."},
    )


class GroupMembershipExtendForm(forms.Form):
    """Form for extending group membership."""

    extend_length = forms.IntegerField(
        label="Extend by (in days)",
        min_value=1,
    )
