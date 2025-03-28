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


def test_check_ldap_consistency_success(
    ldap_connection_mock, rdf_allocation, allocation_user, mocker
):
    """Test check_ldap_consistency when everything is in sync."""
    group_id = rdf_allocation.allocationattribute_set.get(
        allocation_attribute_type__name="RDF Project ID"
    ).value
    username = allocation_user.user.username

    def search_side_effect(base_dn, filter_query, **kwargs):
        if f"(cn={group_id})" in filter_query:
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
        elif "(cn=rdf-*)" in filter_query:
            return (True, None, [{"attributes": {"cn": [group_id]}}], None)
        return (True, None, [{"dn": username}], None)

    ldap_connection_mock().search.side_effect = search_side_effect

    mock_send = mocker.patch(
        "imperial_coldfront_plugin.ldap._send_discrepancy_notification"
    )

    mocker.patch("imperial_coldfront_plugin.ldap.settings.LDAP_ENABLED", True)

    result = check_ldap_consistency()

    assert not result["missing_groups"]
    assert not result["extra_groups"]
    assert not result["membership_discrepancies"]

    mock_send.assert_not_called()


def test_check_ldap_consistency_missing_group(
    ldap_connection_mock, rdf_allocation, allocation_user, mocker
):
    """Test check_ldap_consistency when an AD group is missing."""

    def search_side_effect(base_dn, filter_query, **kwargs):
        if "cn=" in filter_query and "rdf-*" not in filter_query:
            return (True, None, [], None)
        elif "(cn=rdf-*)" in filter_query:
            return (True, None, [], None)
        return (True, None, [{"dn": "user1"}], None)

    ldap_connection_mock().search.side_effect = search_side_effect

    mock_send = mocker.patch(
        "imperial_coldfront_plugin.ldap._send_discrepancy_notification"
    )
    mocker.patch("imperial_coldfront_plugin.ldap.settings.LDAP_ENABLED", True)

    result = check_ldap_consistency()

    assert len(result["missing_groups"]) == 1
    assert result["missing_groups"][0]["allocation_id"] == rdf_allocation.id
    group_id = rdf_allocation.allocationattribute_set.get(
        allocation_attribute_type__name="RDF Project ID"
    ).value
    assert result["missing_groups"][0]["group_id"] == group_id

    mock_send.assert_called_once()


def test_check_ldap_consistency_membership_mismatch(
    ldap_connection_mock, rdf_allocation, allocation_user, mocker
):
    """Test check_ldap_consistency when group membership doesn't match."""
    group_id = rdf_allocation.allocationattribute_set.get(
        allocation_attribute_type__name="RDF Project ID"
    ).value

    def search_side_effect(base_dn, filter_query, **kwargs):
        if f"(cn={group_id})" in filter_query:
            return (
                True,
                None,
                [
                    {
                        "attributes": {
                            "member": ["cn=wrong_user,ou=Users,dc=example,dc=com"]
                        }
                    }
                ],
                None,
            )
        elif "(cn=rdf-*)" in filter_query:
            return (True, None, [{"attributes": {"cn": [group_id]}}], None)
        return (True, None, [{"dn": "user1"}], None)

    ldap_connection_mock().search.side_effect = search_side_effect

    mock_send = mocker.patch(
        "imperial_coldfront_plugin.ldap._send_discrepancy_notification"
    )
    mocker.patch("imperial_coldfront_plugin.ldap.settings.LDAP_ENABLED", True)

    result = check_ldap_consistency()

    assert len(result["membership_discrepancies"]) == 1
    discrepancy = result["membership_discrepancies"][0]
    assert discrepancy["allocation_id"] == rdf_allocation.id
    assert discrepancy["group_id"] == group_id

    assert allocation_user.user.username in discrepancy["missing_members"]
    assert "wrong_user" in discrepancy["extra_members"]

    mock_send.assert_called_once()
