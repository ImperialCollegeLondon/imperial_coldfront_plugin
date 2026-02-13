"""Email tests."""

from django.core import mail
from django.test import override_settings

from imperial_coldfront_plugin.emails import (
    send_fileset_not_found_notification,
    send_quota_discrepancy_notification,
)


@override_settings(ADMINS=[("Name", "admin@email.com")])
def test_send_quota_discrepancy_notification():
    """Test the quota discrepancy email."""
    discrepancies = [
        {
            "shortname": "bio-research-01",
            "attribute_storage_quota": 500,
            "fileset_storage_quota": 550,
            "attribute_files_quota": 1000000,
            "fileset_files_quota": 1200000,
        },
        {
            "shortname": "physics-dept-lab",
            "attribute_storage_quota": 2,
            "fileset_storage_quota": 2.5,
            "attribute_files_quota": None,
            "fileset_files_quota": None,
        },
        {
            "shortname": "chem-analysis",
            "attribute_storage_quota": None,
            "fileset_storage_quota": None,
            "attribute_files_quota": 500000,
            "fileset_files_quota": 600000,
        },
    ]

    expected_message = """\
During a regularly scheduled automated check, a discrepancy was found between the data \
held in Coldfront and fileset quotas in GPFS. These should be in agreement so that \
Coldfront is reporting accurate information to end users. \
Please investigate and reconcile the two.

The following discrepancies were detected between Coldfront and GPFS:

\t- Allocation shortname: bio-research-01
\t\tAllocation storage quota of 500, GPFS storage quota of 550.
\t\tAllocation files quota of 1000000, GPFS files quota of 1200000.
\t- Allocation shortname: physics-dept-lab
\t\tAllocation storage quota of 2, GPFS storage quota of 2.5.
\t- Allocation shortname: chem-analysis
\t\tAllocation files quota of 500000, GPFS files quota of 600000.
"""

    send_quota_discrepancy_notification(discrepancies)

    # Django intercepts emails sent during tests, access them using mail.
    assert len(mail.outbox) == 1
    actual_message = mail.outbox[0].body

    assert actual_message == expected_message


@override_settings(ADMINS=[("Name", "admin@email.com")])
def test_send_fileset_not_found_notification():
    """Test the fileset not found email."""
    shortnames = ["bio-research-01", "physics-dept-lab"]

    expected_message = """\
During a regularly scheduled automated check, an allocation in Coldfront was found \
to have no corresponding fileset in GPFS. These systems should be in agreement \
to ensure that Coldfront is reporting accurate information to end users. Please \
investigate and reconcile the two.

The following allocation(s) in Coldfront had no corresponding fileset in GPFS:
\t- bio-research-01
\t- physics-dept-lab
"""

    send_fileset_not_found_notification(shortnames)

    # Django intercepts emails sent during tests, access them using mail.
    assert len(mail.outbox) == 1
    actual_message = mail.outbox[0].body

    assert actual_message == expected_message
