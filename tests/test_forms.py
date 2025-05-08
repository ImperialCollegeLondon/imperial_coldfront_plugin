from datetime import datetime

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
def rdf_form_data(pi_project):
    """Fixture to provide RDFAllocationForm data."""
    faculty_id = "foe"
    department_id = DEPARTMENTS_IN_FACULTY[faculty_id][0]
    return dict(
        username=pi_project.pi.username,
        faculty=faculty_id,
        department=department_id,
        end_date=datetime.max.date(),
        size=10,
        dart_id="1",
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
