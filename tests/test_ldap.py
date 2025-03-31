from unittest.mock import MagicMock, patch

import ldap3
import pytest

from imperial_coldfront_plugin.ldap import (
    AD_ENTITY_ALREADY_EXISTS_ERROR_CODE,
    AD_WILL_NOT_PERFORM_ERROR_CODE,
    LDAPGroupModifyError,
    _ldap_add_member_to_group,
    _ldap_remove_member_from_group,
    check_ldap_consistency,
    group_dn_from_name,
)

GROUP_NAME = "group_name"
MEMBER_USERNAME = "user1"


def test_ldap_add_member_to_group(ldap_connection_mock):
    """Test _ldap_add_member_to_group."""
    _ldap_add_member_to_group(GROUP_NAME, MEMBER_USERNAME)

    ldap_connection_mock().modify.assert_called_once_with(
        group_dn_from_name(GROUP_NAME),
        dict(member=(ldap3.MODIFY_ADD, [MEMBER_USERNAME])),
    )


def test_ldap_add_member_to_group_allow_existing(ldap_connection_mock):
    """Test allow_already_present option for _ldap_add_member_to_group."""
    ldap_connection_mock().modify.return_value = (
        False,
        dict(result=AD_ENTITY_ALREADY_EXISTS_ERROR_CODE),
        None,
        None,
    )

    _ldap_add_member_to_group(GROUP_NAME, MEMBER_USERNAME, allow_already_present=True)


def test_ldap_add_member_to_group_wrong_error_code(ldap_connection_mock):
    """Test allow_already_present option if an incorrect error code is returned."""
    ldap_connection_mock().modify.return_value = (
        False,
        dict(result=AD_ENTITY_ALREADY_EXISTS_ERROR_CODE + 1),
        None,
        None,
    )
    with pytest.raises(LDAPGroupModifyError):
        _ldap_add_member_to_group(
            GROUP_NAME, MEMBER_USERNAME, allow_already_present=True
        )


def test_ldap_remove_member_from_group(ldap_connection_mock):
    """Test _ldap_remove_member_from_group."""
    _ldap_remove_member_from_group(GROUP_NAME, MEMBER_USERNAME)

    ldap_connection_mock().modify.assert_called_once_with(
        group_dn_from_name(GROUP_NAME),
        dict(member=(ldap3.MODIFY_DELETE, [MEMBER_USERNAME])),
    )


def test_ldap_remove_member_from_group_allow_missing(ldap_connection_mock):
    """Test allow_missing option for _ldap_remove_member_from_group."""
    ldap_connection_mock().modify.return_value = (
        False,
        dict(result=AD_WILL_NOT_PERFORM_ERROR_CODE),
        None,
        None,
    )

    _ldap_remove_member_from_group(GROUP_NAME, MEMBER_USERNAME, allow_missing=True)


def test_ldap_remove_member_from_group_wrong_error_code(ldap_connection_mock):
    """Test allow_missing option if an incorrect error code is returned."""
    ldap_connection_mock().modify.return_value = (
        False,
        dict(result=AD_WILL_NOT_PERFORM_ERROR_CODE + 1),
        None,
        None,
    )
    with pytest.raises(LDAPGroupModifyError):
        _ldap_remove_member_from_group(GROUP_NAME, MEMBER_USERNAME, allow_missing=True)


@patch("imperial_coldfront_plugin.ldap._send_discrepancy_notification")
def test_check_ldap_consistency_no_discrepancies(
    mock_notify, rdf_allocation, allocation_user, ldap_connection_mock
):
    """Test when everything is in sync between Coldfront and AD."""
    group_id = rdf_allocation.allocationattribute_set.get(
        allocation_attribute_type__name="RDF Project ID"
    ).value
    username = allocation_user.user.username

    def mock_search(base_dn, search_filter, **kwargs):
        if f"(cn={group_id})" in search_filter:
            return (
                True,
                None,
                [
                    {
                        "attributes": {
                            "member": [f"cn={username},ou=Users,dc=example,dc=com"]
                        }
                    }
                ],
                None,
            )
        return (True, None, [], None)

    ldap_connection_mock().search.side_effect = mock_search

    with patch("imperial_coldfront_plugin.ldap.re.search") as mock_re_search:

        def side_effect(pattern, string, flags=0):
            if username in string:
                mock_match = MagicMock()
                mock_match.group.return_value = username
                return mock_match
            return None

        mock_re_search.side_effect = side_effect

        result = check_ldap_consistency()

    assert (
        "membership_discrepancies" not in result
        or len(result["membership_discrepancies"]) == 0
    )

    mock_notify.assert_not_called()


@patch("imperial_coldfront_plugin.ldap._send_discrepancy_notification")
def test_check_ldap_consistency_missing_members(
    mock_notify, rdf_allocation, allocation_user, ldap_connection_mock
):
    """Test when a user is missing from AD group."""
    group_id = rdf_allocation.allocationattribute_set.get(
        allocation_attribute_type__name="RDF Project ID"
    ).value
    username = allocation_user.user.username

    # Mock LDAP search to return empty group (no members)
    def mock_search(base_dn, search_filter, **kwargs):
        if f"(cn={group_id})" in search_filter:
            return (
                True,
                None,
                [
                    {
                        "attributes": {
                            "member": []  # Empty member list
                        }
                    }
                ],
                None,
            )
        return (True, None, [], None)

    ldap_connection_mock().search.side_effect = mock_search

    # Call function
    result = check_ldap_consistency()

    # Verify membership discrepancy was detected
    assert "membership_discrepancies" in result
    assert len(result["membership_discrepancies"]) == 1
    discrepancy = result["membership_discrepancies"][0]
    assert discrepancy["allocation_id"] == rdf_allocation.id
    assert discrepancy["group_id"] == group_id
    assert discrepancy["project_name"] == rdf_allocation.project.title
    assert username in discrepancy["missing_members"]
    assert not discrepancy["extra_members"]

    # Verify notification was sent
    mock_notify.assert_called_once()


@patch("imperial_coldfront_plugin.ldap._send_discrepancy_notification")
def test_check_ldap_consistency_extra_members(
    mock_notify, rdf_allocation, allocation_user, ldap_connection_mock
):
    """Test when there are extra users in AD group."""
    group_id = rdf_allocation.allocationattribute_set.get(
        allocation_attribute_type__name="RDF Project ID"
    ).value
    username = allocation_user.user.username
    extra_user = "extra_user"

    # Mock LDAP search to return group with expected user plus an extra one
    def mock_search(base_dn, search_filter, **kwargs):
        if f"(cn={group_id})" in search_filter:
            return (
                True,
                None,
                [
                    {
                        "attributes": {
                            "member": [
                                f"cn={username},ou=Users,dc=example,dc=com",
                                f"cn={extra_user},ou=Users,dc=example,dc=com",
                            ]
                        }
                    }
                ],
                None,
            )
        return (True, None, [], None)

    ldap_connection_mock().search.side_effect = mock_search

    # Patch re.search to correctly extract usernames
    with patch("imperial_coldfront_plugin.ldap.re.search") as mock_re_search:

        def side_effect(pattern, string, flags=0):
            mock_match = MagicMock()
            if username in string:
                mock_match.group.return_value = username
                return mock_match
            elif extra_user in string:
                mock_match.group.return_value = extra_user
                return mock_match
            return None

        mock_re_search.side_effect = side_effect

        # Call function
        result = check_ldap_consistency()

    # Verify membership discrepancy was detected
    assert "membership_discrepancies" in result
    assert len(result["membership_discrepancies"]) == 1
    discrepancy = result["membership_discrepancies"][0]
    assert discrepancy["allocation_id"] == rdf_allocation.id
    assert discrepancy["group_id"] == group_id
    assert not discrepancy["missing_members"]
    assert extra_user in discrepancy["extra_members"]

    # Verify notification was sent
    mock_notify.assert_called_once()
