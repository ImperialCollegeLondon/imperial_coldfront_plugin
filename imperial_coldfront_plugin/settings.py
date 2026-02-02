"""Settings for the Imperial Coldfront plugin.

These are imported into the project level settings by the Coldfront plugin mechanism.
"""

from pathlib import Path
from string import ascii_lowercase, digits

from coldfront.config.env import ENV

from .acl import ACL, ACLEntry

MICROSOFT_TENANT_ID = ENV.str("MICROSOFT_TENANT_ID", default="")
ADDITIONAL_USER_SEARCH_CLASSES = ["imperial_coldfront_plugin.views.GraphAPISearch"]
GPFS_API_URL = ENV.str("GPFS_API_URL", default="")
"""URL of the GPFS server."""
GPFS_API_USERNAME = ENV.str("GPFS_API_USERNAME", default="")
"""Username to access the server."""
GPFS_API_PASSWORD = ENV.str("GPFS_API_PASSWORD", default="")
"""Associated password."""
GPFS_API_VERIFY = ENV.bool("GPFS_API_VERIFY", default=False)
"""If certificate should be verified when connecting to the server.

Need to be False in order to access self-signed certificates.
"""
GPFS_API_TIMEOUT = ENV.int("GPFS_API_TIMEOUT", default=300)
"""Timeout for requests that require creating, deleting or updating resources."""

GPFS_FILESYSTEM_NAME = ENV.str("GPFS_FILESYSTEM_NAME", default="")
"""Name of the GPFS filesystem."""

GPFS_FILESYSTEM_MOUNT_PATH = Path(ENV.str("GPFS_FILESYSTEM_MOUNT_PATH", default=""))
"""Path to the directory in which the filesystem is mounted."""

GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES = Path(
    ENV.str("GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES", default="")
)
"""Top-level directory within a filesystem which contains faculty filesets."""

GPFS_FILESET_POSIX_PERMISSIONS = ENV.str(
    "GPFS_FILESET_POSIX_PERMISSIONS", default="2770"
)
"""Posix permissions for the fileset."""

GPFS_PARENT_DIRECTORY_POSIX_PERMISSIONS = ENV.str(
    "GPFS_PARENT_DIRECTORY_POSIX_PERMISSIONS", default="755"
)
"""Posix permissions for fileset parent directories."""

GPFS_PARENT_DIRECTORY_ACL = ACL(
    owner=[ACLEntry("", "rwmxDaAnNcCos")],
    group=[ACLEntry("", "rxancs")],
    other=[ACLEntry("", "rxancs")],
)
"""ACL data for fileset parent directories."""

GPFS_FILESET_ACL = ACL(
    owner=[
        ACLEntry("", "rwmxDaAnNcCos"),
        ACLEntry("f", "rwmxDaAnNcCos"),
        ACLEntry("d", "rwmxDaAnNcCos"),
    ],
    group=[
        ACLEntry("", "rwmxDanNc"),
        ACLEntry("f", "rwmxdDaAnNcs"),
        ACLEntry("d", "rwmxdDaAnNcs"),
    ],
    other=[ACLEntry("", "ancs")],
)
"""ACL data for filesets."""

GPFS_FILES_QUOTA = ENV.int("GPFS_FILES_QUOTA", default=1000)
"""Quota for the fileset."""

GPFS_ENABLED = bool(GPFS_API_URL and GPFS_API_USERNAME and GPFS_API_PASSWORD)
"""Computed value of whether GPFS integration is enabled."""

LDAP_USERNAME = ENV.str("LDAP_USERNAME", default="")
"""Active Directory user account name."""
LDAP_PASSWORD = ENV.str("LDAP_PASSWORD", default="")
"""Password for LDAP_USERNAME."""
LDAP_URI = ENV.str("LDAP_URI", default="")
"""Active Directory server URI."""
LDAP_USER_OU = ENV.str(
    "LDAP_USER_OU", default="OU=Users,OU=Imperial College (London),dc=ic,dc=ac,dc=uk"
)
"""The organisational unit containing Imperial user data."""
LDAP_GROUP_OU = ENV.str(
    "LDAP_GROUP_OU",
    default="OU=RCS,OU=Groups,OU=Imperial College (London),DC=ic,DC=ac,DC=uk",
)
"""The organisational unit containing RDF access groups."""
LDAP_SHORTNAME_PREFIX = "rdf-"
"""Prefix added to allocation shortname for corresponding Active Directory group."""

AD_DOMAIN = ENV.str("AD_DOMAIN", default="IC")
"""The Active Directory domain."""

LDAP_ENABLED = bool(LDAP_USERNAME and LDAP_PASSWORD and LDAP_URI)
"""Computed value of whether LDAP integration is enabled."""


_GID_RANGES = ENV.str("GID_RANGE", default="1031386-1031435")
GID_RANGES = [
    range(int(start), int(end) + 1)
    for start, end in [gid_range.split("-") for gid_range in _GID_RANGES.split(",")]
]
"""List of ranges of GIDs available for allocation to groups."""

LOGOUT_REDIRECT_URL = "/"

PATH_COMPONENT_VALID_CHARACTERS = set(ascii_lowercase + digits)
"""Characters that are valid to include as part of an allocation shortname."""
ALLOCATION_SHORTNAME_MIN_LENGTH = 3
"""Minimum length of an allocation shortname."""
ALLOCATION_SHORTNAME_MAX_LENGTH = 12
"""Maximum length of an allocation shortname."""
ALLOCATION_DEFAULT_PERIOD_DAYS = 365
"""Days from current date for the initial form default end date for an allocation."""

# RDF Allocation Expiry Notification Schedules
RDF_ALLOCATION_EXPIRY_WARNING_SCHEDULE = [90, 60, 30, 7, 1]
"""Days before expiry to send expiry warning notifications."""

RDF_ALLOCATION_REMOVAL_WARNING_SCHEDULE = [0, -3, -6]
"""Days relative to expiry to send removal warning notifications."""

RDF_ALLOCATION_DELETION_WARNING_SCHEDULE = [-7, -10, -13]
"""Days after expiry to send deletion warning notifications."""

RDF_ALLOCATION_DELETION_NOTIFICATION_SCHEDULE = [-14]
"""Days after expiry to send deletion notifications."""

SHOW_CREDIT_BALANCE = ENV.bool("SHOW_CREDIT_BALANCE", default=False)
"""Whether to display the credit balance section on project detail pages."""

RDF_ALLOCATION_EXPIRY_DELETION_DAYS = 14
"""Number of days after an allocation expiry to delete the allocation automatically."""

# Mappings for faculty and department names and shortnames for development purposes.
# These should be overridden in prod via prod_settings.py.
DEPARTMENTS = {
    "physics": "Physics",
    "dsde": "Dyson School of Design Engineering",
    "chemistry": "Chemistry",
    "aero": "Aeronautics",
}
FACULTIES = {
    "buss": "Business School",
    "facility": "Facility",
    "foe": "Faculty of Engineering",
    "fom": "Faculty of Medicine",
    "fons": "Faculty of Natural Sciences",
    "ict": "ICT",
}
DEPARTMENTS_IN_FACULTY = {
    "foe": ["dsde", "aero"],
    "fons": ["physics", "chemistry"],
}
