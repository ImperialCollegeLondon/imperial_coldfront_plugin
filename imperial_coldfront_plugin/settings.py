"""Settings for the Imperial Coldfront plugin.

These are imported into the project level settings by the Coldfront plugin mechanism.
"""

from datetime import timedelta

INVITATION_TOKEN_TIMEOUT = timedelta(days=7).total_seconds()
