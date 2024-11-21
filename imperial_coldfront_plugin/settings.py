"""Plugin settings that are imported into the global settings namespace of Coldfront."""

from coldfront.config.env import ENV

LDAP_SERVER_URI = ENV.str("LDAP_SERVER_URI", default="")
LDAP_SEARCH_BASE = ENV.str("LDAP_SEARCH_BASE", default="")
