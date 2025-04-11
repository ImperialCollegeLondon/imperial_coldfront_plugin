"""Forms for the Imperial Coldfront plugin.

This module contains form classes used for research group management.
"""

from collections.abc import Iterable

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


DEPARTMENTS = {
    "Physics": "physics",
    "Dyson School of Design Engineering": "dsde",
    "Chemistry": "chemistry",
    "Aeronautics": "aero",
}

FACULTIES = {"Faculty of Engineering": "foe", "Faculty of Natural Sciences": "fons"}

DEPARTMENTS_IN_FACULTY = {
    "foe": ["Dyson School of Design Engineering", "Aeronautics"],
    "fons": ["Physics", "Chemistry"],
}


def get_faculty_choices() -> Iterable[tuple[str, str]]:
    """Get the available faculties."""
    return [("", "--------")] + [(id_, name) for name, id_ in FACULTIES.items()]


def get_department_choices(faculty_id: str) -> Iterable[tuple[str, str]]:
    """Get the available departments for the chosen faculty."""
    if not faculty_id or faculty_id not in DEPARTMENTS_IN_FACULTY:
        return [("", "--------")]
    return [("", "--------")] + [
        (DEPARTMENTS[name], name) for name in DEPARTMENTS_IN_FACULTY[faculty_id]
    ]


def get_initial_department_choices() -> Iterable[tuple[str, str]]:
    """Get all the initial departments in tuple form."""
    return [("", "--------")] + [(id_, name) for name, id_ in DEPARTMENTS.items()]


def is_valid_faculty_department_combination(
    faculty_id: str, department_id: str
) -> bool:
    """Check if the faculty and department combination is valid.

    Args:
        faculty_id: The ID of the faculty.
        department_id: The ID of the department.

    Returns:
        bool: True if the combination is valid, False otherwise.
    """
    dep = {value: key for key, value in DEPARTMENTS.items()}.get(department_id)
    return dep in DEPARTMENTS_IN_FACULTY.get(faculty_id, [])


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
        choices=get_initial_department_choices,
        widget=forms.Select(attrs={"class": "js-example-basic-single"}),
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        validators=[MinValueValidator(timezone.now().date())],
    )
    size = forms.IntegerField(
        validators=[MinValueValidator(1)], help_text="In gigabytes"
    )
    dart_id = forms.CharField(
        help_text="The associated DART entry.",
        disabled=False,
    )
