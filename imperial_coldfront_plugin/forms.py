"""Forms for the Imperial Coldfront plugin.

This module contains form classes used for research group management.
"""

from collections.abc import Iterable

from coldfront.core.project.forms import ProjectAddUsersToAllocationForm
from coldfront.core.project.models import Project
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.http.request import QueryDict
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .dart import DartIDValidationError, validate_dart_id
from .microsoft_graph_client import get_graph_api_client
from .utils import get_allocation_shortname

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


def filesystem_path_component_validator(value: str) -> str:
    """Ensure filesystem path components only contain valid chars."""
    if not settings.PATH_COMPONENT_VALID_CHARACTERS.issuperset(value):
        raise ValidationError("Name must contain only lowercase letters or numbers")


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
        min_length=settings.ALLOCATION_SHORTNAME_MIN_LENGTH,
        max_length=settings.ALLOCATION_SHORTNAME_MAX_LENGTH,
        validators=[filesystem_path_component_validator],
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
        from coldfront.core.allocation.models import AllocationAttribute

        if AllocationAttribute.objects.filter(
            allocation_attribute_type__name="Shortname", value=shortname
        ):
            raise ValidationError("Name already in use.")

        return shortname


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
    faculty = forms.ChoiceField(choices=get_faculty_choices)
    department = forms.ChoiceField(choices=get_initial_department_choices)
    group_id = forms.CharField(
        required=False,
        min_length=3,
        max_length=12,
        help_text=(
            "Provide an ID value for the group. This is used as the directory name on "
            "the RDF to contain all allocations of the group. If left blank, the "
            "username field will be used instead. Must contain only lowercase letters "
            "and numbers and be between 3 and 12 characters."
        ),
        label="Group ID",
        validators=[filesystem_path_component_validator],
    )

    def __init__(self, data: QueryDict | None = None, **kwargs):
        """Initialise new form instance.

        Performs some manipulation of the input data such that if group_id is not
        provided the value of username is written into that field.
        """
        if data:
            new_data = data.copy()
            group_id = (
                form_group_id
                if (form_group_id := data.get("group_id"))
                else data.get("username")
            )
            if group_id:
                new_data["group_id"] = group_id
                data = new_data
        super().__init__(data=data, **kwargs)

    def clean_username(self) -> str:
        """Clean username field.

        Tries to map username to a user object and adds a user entry to cleaned_data.
        """
        username = self.cleaned_data["username"]
        try:
            self.cleaned_data["user"] = get_or_create_user(username)
        except UnknownUsernameError:
            raise ValidationError("Username not found locally or in College directory.")
        return username

    def clean_group_id(self) -> str | None:
        """Derive group_id value, check characters and ensure uniqueness."""
        from coldfront.core.project.models import ProjectAttribute

        group_id = self.cleaned_data["group_id"]

        if ProjectAttribute.objects.filter(
            proj_attr_type__name="Group ID", value=group_id
        ):
            raise ValidationError("Name already in use.")
        return group_id

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


class ProjectAddUsersToAllocationShortnameForm(ProjectAddUsersToAllocationForm):
    """Form for adding users to allocations within a project.

    This is an override of a Coldfront form class that we use to customise the display
    of the allocation choices to include the shortname attribute.
    """

    def __init__(self, request_user, project_pk, *args, **kwargs):
        """Initialize the form."""
        super().__init__(request_user, project_pk, *args, **kwargs)
        project_obj = get_object_or_404(Project, pk=project_pk)

        allocation_query_set = project_obj.allocation_set.filter(
            resources__is_allocatable=True,
            is_locked=False,
            status__name__in=[
                "Active",
                "New",
                "Renewal Requested",
                "Payment Pending",
                "Payment Requested",
                "Paid",
            ],
        )
        allocation_choices = [
            (
                allocation.id,
                f"{allocation.get_parent_resource.name} "
                f"({allocation.get_parent_resource.resource_type.name}) "
                f"{get_allocation_shortname(allocation)}",
            )
            for allocation in allocation_query_set
        ]
        allocation_choices_sorted = []
        allocation_choices_sorted = sorted(
            allocation_choices, key=lambda x: x[1][0].lower()
        )
        allocation_choices.insert(0, ("__select_all__", "Select All"))
        if allocation_query_set:
            self.fields["allocation"].choices = allocation_choices_sorted
            self.fields[
                "allocation"
            ].help_text = "<br/>Select allocations to add selected users to."
        else:
            self.fields["allocation"].widget = forms.HiddenInput()
