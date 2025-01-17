"""Plugin forms."""

from django import forms


class GroupMembershipForm(forms.Form):
    """Form for inviting a user to a research group."""

    invitee_email = forms.EmailField(label="Email")


class TermsAndConditionsForm(forms.Form):
    """Form for accepting terms and conditions."""

    accept = forms.BooleanField(
        label="I accept the terms and conditions",
        required=True,
        error_messages={"required": "You must accept the terms and conditions"},
    )
