"""Forms for the Imperial Coldfront plugin.

This module contains form classes used for research group management.
"""

from collections.abc import Iterable

from coldfront.core.project.models import Project
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxLengthValidator,
    MinLengthValidator,
    MinValueValidator,
)
from django.utils import timezone

from .dart import DartIDValidationError, validate_dart_id
from .microsoft_graph_client import get_graph_api_client

User = get_user_model()

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


class UnknownUsernameError(Exception):
    """Unable to locate a user in the local database or College directory."""


def get_or_create_user(username: str) -> User:
    """Get user from the database or creates one using data from Graph.

    Args:
        username: The username of the user to be retrieved or created.

    Return:
        The user, already existing or newly created.
    """
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        pass
    else:
        return user
    client = get_graph_api_client()
    user_data = client.user_profile(username)
    if not user_data["username"]:
        raise UnknownUsernameError(
            f"Unable to find or create user with username: '{username}'"
        )
    return User.objects.create(
        username=user_data["username"],
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        email=user_data["email"],
    )


def _todays_date():
    """Get today's date."""
    return timezone.now().date()


def _js_select_widget():
    """Get a select widget with the class for select2."""
    return forms.Select(attrs={"class": "js-example-basic-single"})


class RDFAllocationForm(forms.Form):
    """Form for creating a new RDF allocation."""

    project = forms.ModelChoiceField(
        queryset=Project.objects.filter(status__name="Active"),
        widget=_js_select_widget(),
    )
    start_date = forms.DateField(
        validators=[MinValueValidator(_todays_date)],
        initial=_todays_date,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        validators=[MinValueValidator(_todays_date)],
        initial=_todays_date,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    faculty = forms.ChoiceField(
        choices=get_faculty_choices,
        widget=_js_select_widget(),
    )
    department = forms.ChoiceField(
        choices=get_initial_department_choices,
        widget=_js_select_widget(),
    )
    size = forms.IntegerField(
        validators=[MinValueValidator(1)], help_text="In terabytes"
    )
    dart_id = forms.CharField(
        help_text="The associated DART entry.",
        disabled=False,
        required=False,
        widget=forms.HiddenInput(),
    )
    allocation_shortname = forms.CharField(
        help_text=(
            "Used to identify individual allocations and in the filesystem path."
            " Lower case letters and numbers only. Must contain between "
            f"{settings.ALLOCATION_SHORTNAME_MIN_LENGTH} and "
            f"{settings.ALLOCATION_SHORTNAME_MAX_LENGTH} characters."
        ),
        validators=[
            MinLengthValidator(settings.ALLOCATION_SHORTNAME_MIN_LENGTH),
            MaxLengthValidator(settings.ALLOCATION_SHORTNAME_MAX_LENGTH),
        ],
    )

    def clean_dart_id(self) -> str:
        """Validate provided Dart ID."""
        dart_id = self.cleaned_data["dart_id"]
        allocation = self.cleaned_data.get("allocation")
        if dart_id:
            try:
                validate_dart_id(dart_id, allocation)
            except DartIDValidationError as e:
                raise ValidationError(e.args[0])
        return dart_id

    def clean_allocation_shortname(self) -> str:
        """Validate allocation shortname contains only valid characters."""
        shortname = self.cleaned_data.get("allocation_shortname")
        if not settings.ALLOCATION_SHORTNAME_VALID_CHARACTERS.issuperset(shortname):
            raise ValidationError("Name must contain only lowercase letters or numbers")
        from coldfront.core.allocation.models import AllocationAttribute

        if AllocationAttribute.objects.filter(
            allocation_attribute_type__name="Shortname", value=shortname
        ):
            raise ValidationError("Name already in use.")

        return shortname

    def clean(self) -> bool:
        """Check if the faculty and department combination is valid.

        Raises:
            ValidationError: If the combination is invalid.
        """
        cleaned_data = super().clean()
        faculty_id = cleaned_data.get("faculty")
        department_id = cleaned_data.get("department")
        if department_id not in DEPARTMENTS_IN_FACULTY.get(faculty_id, []):
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


class ProjectCreationForm(forms.ModelForm):
    """Form for creating a new research group (project)."""

    class Meta:
        """Meta class for the form."""

        model = Project
        fields = ("title", "description", "field_of_science")

    username = forms.CharField(
        help_text="Username of group owner (must be a valid imperial username).",
    )

    def clean_username(self) -> str:
        """Clean username field.

        Tries to map username to a user object and adds a user entry to cleaned_data.
        """
        try:
            self.cleaned_data["user"] = get_or_create_user(
                self.cleaned_data["username"]
            )
        except UnknownUsernameError:
            raise ValidationError("Username not found locally or in College directory.")
