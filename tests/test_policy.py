import pytest

from imperial_coldfront_plugin.policy import (
    PI_ALLOWED_TITLES,
    PI_DISALLOWED_DEPARTMENTS,
    PI_DISALLOWED_TITLE_QUALIFIERS,
    user_eligible_for_hpc_access,
    user_eligible_to_be_pi,
)


def test_user_filter(parsed_profile):
    """Test the user filter passes a valid profile."""
    assert user_eligible_for_hpc_access(parsed_profile)


@pytest.mark.parametrize(
    "override_key, override_value",
    [
        ("user_type", ""),
        ("record_status", ""),
        ("email", None),
        ("name", None),
        ("department", None),
    ],
)
def test_user_filter_invalid(override_key, override_value, parsed_profile):
    """Test the user filter catches invalid profiles."""
    parsed_profile[override_key] = override_value
    assert not user_eligible_for_hpc_access(parsed_profile)


@pytest.fixture
def pi_user_profile():
    """Valid user data for a PI."""
    return {
        "record_status": "Live",
        "department": "Department of Computing",
        "employment_status": "Staff",
        "username": "test_user",
        "job_title": "Professor of Computing",
    }


@pytest.mark.parametrize("job_title", PI_ALLOWED_TITLES)
def test_user_eligible_to_be_pi(job_title, pi_user_profile):
    """Test the user filter passes a valid profile."""
    assert user_eligible_to_be_pi(pi_user_profile | dict(job_title=job_title))


@pytest.mark.parametrize(
    "override_key, override_value",
    [
        ("record_status", ""),
        ("employment_status", "whatever"),
    ]
    + [("job_title", qualifier) for qualifier in PI_DISALLOWED_TITLE_QUALIFIERS]
    + [("department", department) for department in PI_DISALLOWED_DEPARTMENTS],
)
def test_user_eligible_to_be_pi_invalid(override_key, override_value, pi_user_profile):
    """Test the pi filter catches invalid profiles."""
    assert not user_eligible_to_be_pi(pi_user_profile | {override_key: override_value})
