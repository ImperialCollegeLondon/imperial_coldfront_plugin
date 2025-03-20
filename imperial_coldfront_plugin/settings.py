"""Settings for the Imperial Coldfront plugin.

These are imported into the project level settings by the Coldfront plugin mechanism.
"""

from datetime import timedelta

from coldfront.config.env import ENV

INVITATION_TOKEN_TIMEOUT = timedelta(days=7).total_seconds()
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

GPFS_FILESYSTEM_NAME = ENV.str("GPFS_API_FILESYSTEM_NAME", default="")
"""Name of the GPFS filesystem."""

GPFS_PERMISSIONS = ENV.str("GPFS_API_PERMISSIONS", default="700")
"""Permissions for the fileset."""

GPFS_FILES_QUOTA = ENV.int("GPFS_API_FILES_QUOTA", default=1000)
"""Quota for the fileset."""

GPFS_ENABLED = bool(GPFS_FILESYSTEM_NAME and GPFS_PERMISSIONS and GPFS_FILES_QUOTA)

EXPIRATION_NOTIFICATION_DAYS = [1, 5, 30]

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

LDAP_ENABLED = bool(LDAP_USERNAME and LDAP_PASSWORD and LDAP_URI)
