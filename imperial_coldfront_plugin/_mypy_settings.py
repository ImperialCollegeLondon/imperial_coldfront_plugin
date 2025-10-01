"""This module is used by mypy to get type info for settings during checking.

Needless to say you should not import this module at runtime or use it for any other
purpose.
"""

import os

# These shenanigans are necessary because the Coldfront OIDC plugin settings require
# these env vars to be set. This won't always be the case (particularly in CI)
# environments so we just set them to empty strings here
os.environ["OIDC_RP_CLIENT_ID"] = ""
os.environ["OIDC_RP_CLIENT_SECRET"] = ""

from coldfront.config.settings import *  # noqa: F403

from .settings import *  # noqa: F403

# the mypy django plugin isn't properly able to infer these settings
# so we need to declare them here for type checking purposes
EMAIL_SENDER = ""
EMAIL_ADMIN_LIST = ""
