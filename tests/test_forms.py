import pytest

from imperial_coldfront_plugin.forms import (
    DEPARTMENTS,
    DEPARTMENTS_IN_FACULTY,
    FACULTIES,
    get_department_choices,
    get_faculty_choices,
    get_initial_department_choices,
)


def test_get_faculty_choices():
    """Test that get_faculty_choices returns the correct choices."""
    expected_choices = [("", "--------")] + [
        (id_, name) for name, id_ in FACULTIES.items()
    ]
    assert get_faculty_choices() == expected_choices


@pytest.mark.parametrize(
    "faculty_id, expected_choices",
    [
        (
            "foe",
            [("", "--------")]
            + [(DEPARTMENTS[name], name) for name in DEPARTMENTS_IN_FACULTY["foe"]],
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
    expected_choices = [("", "--------")] + [
        (id_, name) for name, id_ in DEPARTMENTS.items()
    ]
    assert get_initial_department_choices() == expected_choices
