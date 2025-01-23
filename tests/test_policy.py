import pytest

from imperial_coldfront_plugin.policy import user_eligible_for_hpc_access


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
