"""Email reporter for Coldfront system monitor."""

import sys
import traceback

from django.conf import settings
from django.core.mail import send_mail


class EmailReporter:
    """Simple email reporter for Coldfront system monitor."""

    def report(self) -> None:
        """Send an email report."""
        _, _, tb = sys.exc_info()

        tb_txt = "".join(traceback.format_tb(tb))

        send_mail(
            "Error in Coldfront job queue",
            f"""An error occurred whilst processing a job.
{tb_txt}
            """,
            settings.EMAIL_SENDER,
            settings.EMAIL_ADMIN_LIST.split(","),
            fail_silently=False,
        )
