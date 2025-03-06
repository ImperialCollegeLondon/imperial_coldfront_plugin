"""Settings for the Imperial Coldfront plugin.

These are imported into the project level settings by the Coldfront plugin mechanism.
"""

from datetime import timedelta

from coldfront.config.env import ENV

INVITATION_TOKEN_TIMEOUT = timedelta(days=7).total_seconds()
MICROSOFT_TENANT_ID = ENV.str("MICROSOFT_TENANT_ID", default="")
ADDITIONAL_USER_SEARCH_CLASSES = ["imperial_coldfront_plugin.views.GraphAPISearch"]
GPFS_API_URL = ENV.str("GPFS_API_URL", default="")
GPFS_API_USERNAME = ENV.str("GPFS_API_USERNAME", default="")
GPFS_API_PASSWORD = ENV.str("GPFS_API_PASSWORD", default="")
GPFS_API_VERIFY = ENV.bool("GPFS_API_VERIFY", default=False)

EXPIRATION_NOTIFICATION_DAYS = [1, 5, 30]

LDAP_USERNAME = ENV.str("LDAP_USERNAME", default="")
LDAP_PASSWORD = ENV.str("LDAP_PASSWORD", default="")
LDAP_URI = ENV.str("LDAP_URI", default="")
LDAP_USER_OU = ENV.str(
    "LDAP_USER_OU", default="OU=Users,OU=Imperial College (London),dc=ic,dc=ac,dc=uk"
)
LDAP_GROUP_OU = ENV.str(
    "LDAP_GROUP_OU",
    default="OU=RCS,OU=Groups,OU=Imperial College (London),DC=ic,DC=ac,DC=uk",
)

LDAP_ENABLED = bool(LDAP_USERNAME and LDAP_PASSWORD and LDAP_URI)
