from imperial_coldfront_plugin.acl import ACL, ACLEntry


def test_acl_iter_as_dicts():
    """Test ACL.iter_as_dicts method."""
    acl = ACL(
        owner=[
            ACLEntry(flags="f", permissions="rwmxDaAnNcCos"),
            ACLEntry(flags="d", permissions="rwaDxtTnNcCy", type="deny"),
        ],
        group=[ACLEntry(flags="", permissions="ancs")],
        other=[ACLEntry(flags="d", permissions="rwaDxtTnNcCy")],
    )

    expected = [
        {
            "type": "allow",
            "who": "special:owner@",
            "permissions": "rwmxDaAnNcCos",
            "flags": "f",
        },
        {
            "type": "deny",
            "who": "special:owner@",
            "permissions": "rwaDxtTnNcCy",
            "flags": "d",
        },
        {"type": "allow", "who": "special:group@", "permissions": "ancs", "flags": ""},
        {
            "type": "allow",
            "who": "special:everyone@",
            "permissions": "rwaDxtTnNcCy",
            "flags": "d",
        },
    ]

    assert list(acl.iter_as_dicts()) == expected
