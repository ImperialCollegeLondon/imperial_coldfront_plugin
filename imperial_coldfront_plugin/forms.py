"""Plugin forms."""

from django import forms


class GroupMembershipForm(forms.Form):
    """Form for inviting a user to a research group."""

    invitee_email = forms.EmailField(label="Email")
