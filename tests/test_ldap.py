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


def test_check_ldap_consistency_no_discrepancies(
    rdf_allocation, allocation_user, ldap_connection_mock, rdf_allocation_ldap_name
):
    """Test when everything is in sync between Coldfront and AD."""
    username = allocation_user.user.username

    def mock_search(base_dn, search_filter, **kwargs):
        if f"(cn={rdf_allocation_ldap_name})" in search_filter:
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

        with patch(
            "imperial_coldfront_plugin.ldap._send_discrepancy_notification"
        ) as mock_notify:
            result = check_ldap_consistency()

    assert result == []

    mock_notify.assert_not_called()


def test_check_ldap_consistency_missing_members(
    rdf_allocation, allocation_user, ldap_connection_mock, rdf_allocation_ldap_name
):
    """Test when a user is missing from AD group."""
    username = allocation_user.user.username

    def mock_search(base_dn, search_filter, **kwargs):
        if f"(cn={rdf_allocation_ldap_name})" in search_filter:
            return (
                True,
                None,
                [{"attributes": {"member": []}}],
                None,
            )
        return (True, None, [], None)

    ldap_connection_mock().search.side_effect = mock_search

    with patch(
        "imperial_coldfront_plugin.ldap._send_discrepancy_notification"
    ) as mock_notify:
        result = check_ldap_consistency()

    assert len(result) == 1
    discrepancy = result[0]
    assert discrepancy["allocation_id"] == rdf_allocation.id
    assert discrepancy["group_name"] == rdf_allocation_ldap_name
    assert discrepancy["project_name"] == rdf_allocation.project.title
    assert username in discrepancy["missing_members"]
    assert not discrepancy["extra_members"]

    mock_notify.assert_called_once()


def test_check_ldap_consistency_extra_members(
    rdf_allocation, allocation_user, ldap_connection_mock, rdf_allocation_ldap_name
):
    """Test when there are extra users in AD group."""
    username = allocation_user.user.username
    extra_user = "extra_user"

    def mock_search(base_dn, search_filter, **kwargs):
        if f"(cn={rdf_allocation_ldap_name})" in search_filter:
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

    def side_effect(pattern, string, flags=0):
        mock_match = MagicMock()
        if username in string:
            mock_match.group.return_value = username
            return mock_match
        elif extra_user in string:
            mock_match.group.return_value = extra_user
            return mock_match
        return None

    with (
        patch("imperial_coldfront_plugin.ldap.re.search", side_effect=side_effect),
        patch(
            "imperial_coldfront_plugin.ldap._send_discrepancy_notification"
        ) as mock_notify,
    ):
        result = check_ldap_consistency()

    assert len(result) == 1
    discrepancy = result[0]
    assert discrepancy["allocation_id"] == rdf_allocation.id
    assert discrepancy["group_name"] == rdf_allocation_ldap_name
    assert not discrepancy["missing_members"]
    assert extra_user in discrepancy["extra_members"]

    mock_notify.assert_called_once()
