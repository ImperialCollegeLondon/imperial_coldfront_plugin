"""Forms for the Imperial Coldfront plugin.

This module contains form classes used for research group management.
"""

from django import forms
from django.core.validators import MinValueValidator
from django.utils import timezone


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


def get_project_choices():
    """Populate project choice field options from database."""
    from coldfront.core.project.models import Project

    projects = Project.objects.all()
    return [
        (project.pk, f"{project.pi.get_full_name()} - {project.title}")
        for project in projects
    ]


DEP_FAC_PLACEHOLDER = {
    "Physics": "Natural Sciences",
    "Chemistry": "Natural Sciences",
    "Life Sciences": "Natural Sciences",
    "Aeronautics": "Engineering",
    "Mechanical Engineering": "Engineering",
}


def get_faculty_choices():
    """Get the available faculties."""
    return [(fac, fac) for fac in sorted(set(DEP_FAC_PLACEHOLDER.values()))]


def get_department_choices():
    """Get the available departments."""
    return [(dep, dep) for dep in sorted(DEP_FAC_PLACEHOLDER.keys())]


class RDFAllocationForm(forms.Form):
    """Form for creating a new RDF allocation."""

    project = forms.ChoiceField(
        choices=get_project_choices,
        widget=forms.Select(attrs={"class": "js-example-basic-single"}),
    )
    faculty = forms.ChoiceField(
        choices=get_faculty_choices,
        widget=forms.Select(attrs={"class": "js-example-basic-single"}),
    )
    department = forms.ChoiceField(
        choices=get_department_choices,
        widget=forms.Select(attrs={"class": "js-example-basic-single"}),
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        validators=[MinValueValidator(timezone.now().date())],
    )
    size = forms.IntegerField(
        validators=[MinValueValidator(1)], help_text="In gigabytes"
    )
