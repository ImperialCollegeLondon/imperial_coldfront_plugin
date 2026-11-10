import ldap3
import pytest

from imperial_coldfront_plugin.ldap import (
    AD_ENTITY_ALREADY_EXISTS_ERROR_CODE,
    AD_WILL_NOT_PERFORM_ERROR_CODE,
    LDAPGroupModifyError,
    LDAPResponseError,
    get_cn_from_dn,
    group_dn_from_name,
    ldap_add_member_to_group,
    ldap_get_group_gid,
    ldap_group_member_search,
    ldap_remove_member_from_group,
)

GROUP_NAME = "group_name"
MEMBER_USERNAME = "user1"


@pytest.fixture
def ldap_connection_mock(mocker):
    """Block connections to LDAP server and return simple dummy data."""
    mock = mocker.patch("imperial_coldfront_plugin.ldap.Connection")
    mock().add.return_value = [True, None, None, None]

    def search_side_effect(ou, search_term, *args, **kwargs):
        return None, None, [], None

    mock().search.side_effect = search_side_effect

    mock().modify.return_value = [True, None, None, None]

    return mock


def _make_dn(username):
    return f"CN={username},OU=Users,DC=ic,DC=ac,DC=uk"


@pytest.fixture
def ldap_get_user_dn_mock(mocker):
    """Mock ldap_get_user_dn to return a simple DN based on the username."""

    def _side_effect(username, conn=None):
        return _make_dn(username)

    mock = mocker.patch(
        "imperial_coldfront_plugin.ldap.ldap_get_user_dn", side_effect=_side_effect
    )
    return mock


def test_ldap_add_member_to_group(ldap_connection_mock, ldap_get_user_dn_mock):
    """Test _ldap_add_member_to_group."""
    ldap_add_member_to_group(GROUP_NAME, MEMBER_USERNAME)

    ldap_connection_mock().modify.assert_called_once_with(
        group_dn_from_name(GROUP_NAME),
        dict(member=(ldap3.MODIFY_ADD, [_make_dn(MEMBER_USERNAME)])),
    )


def test_ldap_add_member_to_group_allow_existing(
    ldap_connection_mock, ldap_get_user_dn_mock
):
    """Test allow_already_present option for _ldap_add_member_to_group."""
    ldap_connection_mock().modify.return_value = (
        False,
        dict(result=AD_ENTITY_ALREADY_EXISTS_ERROR_CODE),
        None,
        None,
    )

    ldap_add_member_to_group(GROUP_NAME, MEMBER_USERNAME, allow_already_present=True)


def test_ldap_add_member_to_group_wrong_error_code(ldap_connection_mock):
    """Test allow_already_present option if an incorrect error code is returned."""
    ldap_connection_mock().modify.return_value = (
        False,
        dict(result=AD_ENTITY_ALREADY_EXISTS_ERROR_CODE + 1),
        None,
        None,
    )
    with pytest.raises(LDAPGroupModifyError):
        ldap_add_member_to_group(
            GROUP_NAME, MEMBER_USERNAME, allow_already_present=True
        )


def test_ldap_remove_member_from_group(ldap_connection_mock, ldap_get_user_dn_mock):
    """Test _ldap_remove_member_from_group."""
    ldap_remove_member_from_group(GROUP_NAME, MEMBER_USERNAME)

    ldap_connection_mock().modify.assert_called_once_with(
        group_dn_from_name(GROUP_NAME),
        dict(member=(ldap3.MODIFY_DELETE, [_make_dn(MEMBER_USERNAME)])),
    )


def test_ldap_remove_member_from_group_allow_missing(
    ldap_connection_mock, ldap_get_user_dn_mock
):
    """Test allow_missing option for _ldap_remove_member_from_group."""
    ldap_connection_mock().modify.return_value = (
        False,
        dict(result=AD_WILL_NOT_PERFORM_ERROR_CODE),
        None,
        None,
    )

    ldap_remove_member_from_group(GROUP_NAME, MEMBER_USERNAME, allow_missing=True)


def test_ldap_remove_member_from_group_wrong_error_code(ldap_connection_mock):
    """Test allow_missing option if an incorrect error code is returned."""
    ldap_connection_mock().modify.return_value = (
        False,
        dict(result=AD_WILL_NOT_PERFORM_ERROR_CODE + 1),
        None,
        None,
    )
    with pytest.raises(LDAPGroupModifyError):
        ldap_remove_member_from_group(GROUP_NAME, MEMBER_USERNAME, allow_missing=True)


def _mock_search_conn(mocker, response):
    conn = mocker.Mock()
    conn.search.return_value = (None, None, response, None)
    return conn


def test_ldap_get_group_gid(mocker):
    """Test that an integer gidNumber is returned."""
    conn = _mock_search_conn(mocker, [{"attributes": {"gidNumber": 12345}}])

    assert ldap_get_group_gid("my-group", conn=conn) == 12345


def test_ldap_get_group_gid_no_group(mocker):
    """Test that None is returned when the group does not exist."""
    conn = _mock_search_conn(mocker, [])

    assert ldap_get_group_gid("my-group", conn=conn) is None


@pytest.mark.parametrize(
    "attributes",
    [{}, {"gidNumber": []}, {"gidNumber": "12345"}, {"gidNumber": [12345]}],
    ids=["missing", "empty-list", "string", "list"],
)
def test_ldap_get_group_gid_malformed(mocker, attributes):
    """Test that a missing or non-integer gidNumber raises an error."""
    conn = _mock_search_conn(mocker, [{"attributes": attributes}])

    with pytest.raises(LDAPResponseError):
        ldap_get_group_gid("my-group", conn=conn)


@pytest.mark.parametrize(
    "dn", ["CN=user1,OU=Users,DC=ic", "cn=user1,ou=Users,dc=ic"], ids=["ad", "openldap"]
)
def test_get_cn_from_dn(dn):
    """Test that the common name is extracted regardless of attribute case."""
    assert get_cn_from_dn(dn) == "user1"


def test_get_cn_from_dn_no_cn():
    """Test that a dn without a common name raises an error."""
    with pytest.raises(LDAPResponseError):
        get_cn_from_dn("OU=Users,DC=ic,DC=ac,DC=uk")


def test_ldap_group_member_search(mocker):
    """Test that group names and members are taken from their dns."""
    conn = _mock_search_conn(
        mocker,
        [
            {
                "dn": group_dn_from_name(GROUP_NAME),
                "attributes": {"member": [_make_dn(MEMBER_USERNAME)]},
            }
        ],
    )

    assert ldap_group_member_search(GROUP_NAME, conn=conn) == {
        GROUP_NAME: [MEMBER_USERNAME]
    }
