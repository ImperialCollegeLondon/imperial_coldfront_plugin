from django import forms

class ResearchGroupForm(forms.Form):
    """Form with terms acceptance checkbox and group name input."""

    name = forms.CharField(max_length=255, label="Research Group name", required=True)
    accept_terms = forms.BooleanField(
        required=True, label="I accept the terms and conditions"

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

    search = forms.CharField(label="Search")


class GroupMembershipExtendForm(forms.Form):
    """Form for extending group membership."""

    extend_length = forms.IntegerField(
        label="Extend by (in days)",
        min_value=1,
        main
    )
