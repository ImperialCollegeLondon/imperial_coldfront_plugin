"""Data structures for representing ACLs (Access Control Lists)."""

from collections.abc import Generator
from dataclasses import dataclass


@dataclass
class ACLEntry:
    """Access Control List entry."""

    flags: str
    permissions: str
    type: str = "allow"


@dataclass
class ACL:
    """Access Control List for a directory or fileset."""

    owner: list[ACLEntry]
    group: list[ACLEntry]
    other: list[ACLEntry]

    def iter_as_dicts(self) -> Generator[dict[str, str], None, None]:
        """Iterate over the ACL entries as dictionaries for use with GPFS API."""
        for who, acls in zip(
            ("special:owner@", "special:group@", "special:everyone@"),
            (self.owner, self.group, self.other),
        ):
            for acl in acls:
                yield dict(
                    type=acl.type, who=who, permissions=acl.permissions, flags=acl.flags
                )
