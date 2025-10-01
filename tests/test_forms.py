from datetime import datetime, timedelta
from random import choices

import pytest

from imperial_coldfront_plugin.forms import (
    DEPARTMENTS,
    DEPARTMENTS_IN_FACULTY,
    FACULTIES,
    ProjectCreationForm,
    RDFAllocationForm,
    get_department_choices,
    get_faculty_choices,
    get_initial_department_choices,
)


def test_get_faculty_choices():
    """Test that get_faculty_choices returns the correct choices."""
    expected_choices = [("", "--------"), *FACULTIES.items()]
    assert get_faculty_choices() == expected_choices


@pytest.mark.parametrize(
    "faculty_id, expected_choices",
    [
        (
            "foe",
            [("", "--------")]
            + [(id_, DEPARTMENTS[id_]) for id_ in DEPARTMENTS_IN_FACULTY["foe"]],
        ),
        ("invalid_id", [("", "--------")]),
        ("", [("", "--------")]),
    ],
)
def test_get_department_choices(faculty_id, expected_choices):
    """Test get_department_choices with various faculty IDs."""
    assert get_department_choices(faculty_id) == expected_choices


def test_get_initial_department_choices():
    """Test that get_initial_department_choices returns the correct choices."""
    expected_choices = [("", "--------"), *DEPARTMENTS.items()]
    assert get_initial_department_choices() == expected_choices


@pytest.fixture
def rdf_form_data(project):
    """Fixture to provide RDFAllocationForm data."""
    faculty_id = "foe"
    department_id = DEPARTMENTS_IN_FACULTY[faculty_id][0]
    return dict(
        project=project.pk,
        faculty=faculty_id,
        department=department_id,
        start_date=datetime.now().date(),
        end_date=datetime.max.date(),
        size=10,
        allocation_shortname="shorty",
        description="The allocation description",
    )


def test_rdf_allocation_form_invalid_dart_id(rdf_form_data):
    """Test that validation is being applied to dart_id field."""
    rdf_form_data["dart_id"] = "-1"
    form = RDFAllocationForm(data=rdf_form_data)
    assert not form.is_valid()
    assert form.errors == dict(dart_id=["Dart ID outside valid range"])


PATH_COMPONENT_COMBINATIONS = (
    ("abcd", True),
    ("123", True),
    ("abc123", True),
    ("12AOE", False),
    ("ab_", False),
    ("$tete", False),
    ("tete$", False),
)


@pytest.mark.parametrize("shortname,passes", PATH_COMPONENT_COMBINATIONS)
def test_rdf_allocation_shortname_characters(shortname, passes, db):
    """Test that valid characters are being checked for allocation_shortname field."""
    form = RDFAllocationForm(data=dict(allocation_shortname=shortname))
    form.is_valid()
    if passes:
        assert not form.errors.get("allocation_shortname")
    else:
        assert form.errors["allocation_shortname"] == [
            "Name must contain only lowercase letters or numbers"
        ]


def test_rdf_allocation_unique(project, rdf_allocation, rdf_allocation_shortname):
    """Test that uniqueness is being checked for allocation_shortname field."""
    form = RDFAllocationForm(data=dict(allocation_shortname=rdf_allocation_shortname))
    form.is_valid()
    assert form.errors["allocation_shortname"] == ["Name already in use."]


def test_rdf_allocation_shortname_min_length(settings):
    """Test that min length is being checked for allocation_shortname field."""
    min_length = settings.ALLOCATION_SHORTNAME_MIN_LENGTH
    test_length = min_length - 1
    shortname = "".join(
        choices(list(settings.PATH_COMPONENT_VALID_CHARACTERS), k=test_length)
    )
    form = RDFAllocationForm(data=dict(allocation_shortname=shortname))
    form.is_valid()
    assert form.errors["allocation_shortname"] == [
        f"Ensure this value has at least {min_length} characters (it has {test_length})"
        "."
    ]


def test_rdf_allocation_shortname_max_length(settings):
    """Test that max length is being checked for allocation_shortname field."""
    max_length = settings.ALLOCATION_SHORTNAME_MAX_LENGTH
    test_length = max_length + 1
    shortname = "".join(
        choices(list(settings.PATH_COMPONENT_VALID_CHARACTERS), k=test_length)
    )
    form = RDFAllocationForm(data=dict(allocation_shortname=shortname))
    form.is_valid()
    assert form.errors["allocation_shortname"] == [
        f"Ensure this value has at most {max_length} characters (it has {test_length})."
    ]


def test_rdf_allocation_end_date_initial_value(rdf_form_data, settings):
    """Test that the default end_date is set correctly."""
    form = RDFAllocationForm(data=rdf_form_data)
    assert form["end_date"].initial == datetime.now().date() + timedelta(
        days=settings.ALLOCATION_DEFAULT_PERIOD_DAYS
    )


@pytest.fixture
def get_graph_api_client_mock(mocker, parsed_profile):
    """Mock out imperial_coldfront_plugin.forms.get_graph_api_client."""
    mock = mocker.patch("imperial_coldfront_plugin.forms.get_graph_api_client")
    mock().user_profile.return_value = parsed_profile
    mock().user_search_by.return_value = [parsed_profile]
    return mock


def test_get_or_create_user(
    get_graph_api_client_mock, parsed_profile, django_user_model
):
    """Test get_or_create_user function."""
    from imperial_coldfront_plugin.forms import get_or_create_user

    assert not django_user_model.objects.filter(username=parsed_profile["username"])
    user = get_or_create_user(parsed_profile["username"])
    assert user == django_user_model.objects.get(username=parsed_profile["username"])


@pytest.fixture
def project_form_data(user):
    """Fixture to provide RDFAllocationForm data."""
    from coldfront.core.field_of_science.models import FieldOfScience

    field_of_science_other, _ = FieldOfScience.objects.get_or_create(
        description="Other"
    )

    faculty_id = "foe"
    department_id = DEPARTMENTS_IN_FACULTY[faculty_id][0]

    return dict(
        title="project title",
        description="A description fdor the project",
        field_of_science=field_of_science_other.pk,
        username=user.username,
        faculty=faculty_id,
        department=department_id,
    )


def test_project_form_clean_valid_combination(project_form_data):
    """Test that RDFAllocationForm.clean() raises a ValidationError."""
    form = ProjectCreationForm(data=project_form_data)
    assert form.is_valid()


def test_project_form_clean_invalid_combination(project_form_data):
    """Test that RDFAllocationForm.clean() raises a ValidationError."""
    # choose department from a different faculty
    project_form_data["department"] = DEPARTMENTS_IN_FACULTY["fons"][0]
    form = ProjectCreationForm(data=project_form_data)
    assert not form.is_valid()
    assert form.errors == dict(__all__=["Invalid faculty and department combination."])


def test_project_form_group_id_blank(project_form_data):
    """Test that group_id value is derived from username if blank."""
    form = ProjectCreationForm(data=project_form_data)
    assert form.is_valid()
    assert form.cleaned_data["group_id"] == project_form_data["username"]


@pytest.mark.parametrize("group_id,passes", PATH_COMPONENT_COMBINATIONS)
def test_project_form_group_id_characters(group_id, passes, db, project_form_data):
    """Test that valid characters are being checked for group_id field."""
    project_form_data["group_id"] = group_id
    form = ProjectCreationForm(data=project_form_data)
    form.is_valid()
    if passes:
        assert not form.errors.get("group_id")
    else:
        assert form.errors["group_id"] == [
            "Name must contain only lowercase letters or numbers"
        ]


def test_project_form_group_id_min_length(settings, project_form_data):
    """Test that min length is being checked for allocation_shortname field."""
    project_form_data["group_id"] = "".join(
        choices(list(settings.PATH_COMPONENT_VALID_CHARACTERS), k=2)
    )
    form = ProjectCreationForm(data=project_form_data)
    form.is_valid()
    assert form.errors["group_id"] == [
        "Ensure this value has at least 3 characters (it has 2)."
    ]


def test_project_form_group_id_max_length(settings, project_form_data):
    """Test that max length is being checked for allocation_shortname field."""
    project_form_data["group_id"] = "".join(
        choices(list(settings.PATH_COMPONENT_VALID_CHARACTERS), k=13)
    )
    form = ProjectCreationForm(data=project_form_data)
    form.is_valid()
    assert form.errors["group_id"] == [
        "Ensure this value has at most 12 characters (it has 13)."
    ]


def test_project_form_group_id_from_username_validation(
    project_form_data, get_graph_api_client_mock
):
    """Test that group_id is validated even if it is derived from the username."""
    project_form_data["username"] = "(£(£invalid"
    form = ProjectCreationForm(data=project_form_data)
    assert not form.is_valid()
    form.errors["group_id"] == "Name must contain only lowercase letters or numbers"


def test_project_form_group_id_from_username_validation_chars(
    project_form_data, get_graph_api_client_mock
):
    """Test that group_id chars are validated even when derived from the username."""
    project_form_data["username"] = "(£(£invalid"
    form = ProjectCreationForm(data=project_form_data)
    assert not form.is_valid()
    form.errors["group_id"] == "Name must contain only lowercase letters or numbers"


def test_project_form_group_id_from_username_validation_length(
    project_form_data, get_graph_api_client_mock
):
    """Test that group_id lengeth is validated even when derived from the username."""
    project_form_data["username"] = "ao"
    form = ProjectCreationForm(data=project_form_data)
    assert not form.is_valid()
    form.errors["group_id"] == ["Must be between 3 and 12 characters."]


def test_project_form_group_id_unique(project, project_form_data):
    """Test that uniqueness is being checked for group_id field."""
    project_form_data["group_id"] = project.pi.username
    form = ProjectCreationForm(data=project_form_data)
    assert not form.is_valid()
    assert form.errors["group_id"] == ["Name already in use."]


def test_project_form_group_id_overrides_username(project_form_data):
    """Test that group_id value overrides username if provided."""
    group_id = "override"
    project_form_data["group_id"] = group_id
    form = ProjectCreationForm(data=project_form_data)
    assert form.is_valid()
    assert form.cleaned_data["group_id"] == group_id


def test_project_form_group_id_without_username(project_form_data):
    """Test that group_id is picked up even if username is not provided."""
    del project_form_data["username"]
    group_id = "groupgroup"
    project_form_data["group_id"] = group_id
    form = ProjectCreationForm(data=project_form_data)
    assert not form.is_valid()
    assert form.cleaned_data["group_id"] == group_id
    assert "group_id" not in form.errors
