"""Settings for the Imperial Coldfront plugin.

These are imported into the project level settings by the Coldfront plugin mechanism.
"""

from datetime import timedelta

from coldfront.config.env import ENV

INVITATION_TOKEN_TIMEOUT = timedelta(days=7).total_seconds()
MICROSOFT_TENANT_ID = ENV.str("MICROSOFT_TENANT_ID", default="")
MEMBERSHIP_EXPIRATION_DAYS = [1, 5, 30]
