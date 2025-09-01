from datetime import datetime
from random import choices

import pytest

from imperial_coldfront_plugin.forms import (
    DEPARTMENTS,
    DEPARTMENTS_IN_FACULTY,
    FACULTIES,
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
    )


def test_rdf_allocation_form_clean_valid_combination(rdf_form_data):
    """Test that RDFAllocationForm.clean() raises a ValidationError."""
    form = RDFAllocationForm(data=rdf_form_data)
    assert form.is_valid()


def test_rdf_allocation_form_clean_invalid_combination(rdf_form_data):
    """Test that RDFAllocationForm.clean() raises a ValidationError."""
    # choose department from a different faculty
    rdf_form_data["department"] = DEPARTMENTS_IN_FACULTY["fons"][0]
    form = RDFAllocationForm(data=rdf_form_data)
    assert not form.is_valid()
    assert form.errors == dict(__all__=["Invalid faculty and department combination."])


def test_rdf_allocation_form_invalid_dart_id(rdf_form_data):
    """Test that validation is being applied to dart_id field."""
    rdf_form_data["dart_id"] = "-1"
    form = RDFAllocationForm(data=rdf_form_data)
    assert not form.is_valid()
    assert form.errors == dict(dart_id=["Dart ID outside valid range"])


@pytest.mark.parametrize(
    "shortname,passes",
    (
        ("abcd", True),
        ("123", True),
        ("abc123", True),
        ("12AOE", False),
        ("ab_", False),
        ("$tete", False),
        ("tete$", False),
    ),
)
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
        choices(list(settings.ALLOCATION_SHORTNAME_VALID_CHARACTERS), k=test_length)
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
        choices(list(settings.ALLOCATION_SHORTNAME_VALID_CHARACTERS), k=test_length)
    )
    form = RDFAllocationForm(data=dict(allocation_shortname=shortname))
    form.is_valid()
    assert form.errors["allocation_shortname"] == [
        f"Ensure this value has at most {max_length} characters (it has {test_length})."
    ]


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
