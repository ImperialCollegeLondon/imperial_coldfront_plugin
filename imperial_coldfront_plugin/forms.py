"""Forms for the Imperial Coldfront plugin.

This module contains form classes used for research group management.
"""

from collections.abc import Iterable

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils import timezone

from .dart import DartIDValidationError, validate_dart_id

DEPARTMENTS = {
    "physics": "Physics",
    "dsde": "Dyson School of Design Engineering",
    "chemistry": "Chemistry",
    "aero": "Aeronautics",
}

FACULTIES = {"foe": "Faculty of Engineering", "fons": "Faculty of Natural Sciences"}

DEPARTMENTS_IN_FACULTY = {
    "foe": ["dsde", "aero"],
    "fons": ["physics", "chemistry"],
}


def get_faculty_choices() -> Iterable[tuple[str, str]]:
    """Get the available faculties."""
    return [("", "--------"), *FACULTIES.items()]


def get_department_choices(faculty_id: str) -> Iterable[tuple[str, str]]:
    """Get the available departments for the chosen faculty."""
    if not faculty_id or faculty_id not in DEPARTMENTS_IN_FACULTY:
        return [("", "--------")]
    return [("", "--------")] + [
        (id_, DEPARTMENTS[id_]) for id_ in DEPARTMENTS_IN_FACULTY[faculty_id]
    ]


def get_initial_department_choices() -> Iterable[tuple[str, str]]:
    """Get all the initial departments in tuple form."""
    return [("", "--------"), *DEPARTMENTS.items()]


class RDFAllocationForm(forms.Form):
    """Form for creating a new RDF allocation."""

    username = forms.CharField(
        help_text="Name of the user associated to this allocation.",
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
        validators=[MinValueValidator(1)], help_text="In terabytes"
    )
    dart_id = forms.CharField(
        help_text="The associated DART entry.",
        disabled=False,
    )

    def clean_dart_id(self) -> str:
        """Validate provided Dart ID."""
        dart_id = self.cleaned_data["dart_id"]
        allocation = self.cleaned_data.get("allocation")
        try:
            validate_dart_id(dart_id, allocation)
        except DartIDValidationError as e:
            raise ValidationError(e.args[0])
        return dart_id

    def clean(self) -> bool:
        """Check if the faculty and department combination is valid.

        Raises:
            ValidationError: If the combination is invalid.
        """
        cleaned_data = super().clean()
        faculty_id = cleaned_data["faculty"]
        department_id = cleaned_data["department"]
        if department_id not in DEPARTMENTS_IN_FACULTY[faculty_id]:
            raise ValidationError("Invalid faculty and department combination.")


class DartIDForm(forms.Form):
    """Form for collection of a Dart ID value."""

    dart_id = forms.CharField(disabled=False)

    def clean_dart_id(self) -> str:
        """Validate provided Dart ID."""
        dart_id = self.cleaned_data["dart_id"]
        allocation = self.cleaned_data.get("allocation")
        try:
            validate_dart_id(dart_id, allocation)
        except DartIDValidationError as e:
            raise ValidationError(e.args[0])
        return dart_id
