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
GPFS_API_TIMEOUT = ENV.int("GPFS_API_TIMEOUT", default=60)
"""Timeout for requests that require creating, deleting or updating resources."""
EXPIRATION_NOTIFICATION_DAYS = [1, 5, 30]
