"""Data structures for representing ACLs (Access Control Lists)."""

from collections.abc import Generator
from dataclasses import dataclass


@dataclass
class ACLEntry:
    """Access Control List entry.

    Args:
      flags: ACL flags for the entry
      permissions: ACL permission bits for the entry e.g. "rxancs"
      type: ACL entry type, either "allow" or "deny".
    """

    flags: str
    permissions: str
    type: str = "allow"


@dataclass
class ACL:
    """Access Control List for a directory or fileset.

    Args:
        owner: List of ACL entries for the owner.
        group: List of ACL entries for the group.
        other: List of ACL entries for others.
    """

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
