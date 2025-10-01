"""This module is used by mypy to get type info for settings during checking.

Needless to say you should not import this module at runtime or use it for any other
purpose.
"""

import os

# Disable oidc plugin to avoid needing to set OIDC env vars
os.environ["PLUGIN_AUTH_OIDC"] = "False"

from coldfront.config.settings import *  # noqa: F403

from .settings import *  # noqa: F403

# the mypy django plugin isn't properly able to infer these settings
# so we need to declare them here for type checking purposes
EMAIL_SENDER = ""
EMAIL_ADMIN_LIST = ""
OIDC_RP_CLIENT_ID = ""
OIDC_RP_CLIENT_SECRET = ""
