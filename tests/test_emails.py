"""Email tests."""

import textwrap
from string import Template

import pytest
from django.core import mail
from django.test import override_settings

from imperial_coldfront_plugin.emails import (
    Discrepancy,
    DiscrepancyCheckResult,
    notify_platforms_to_manually_delete_allocation,
    send_discrepancy_notification,
    send_fileset_not_found_notification,
    send_hx2_access_group_discrepancy_notification,
    send_quota_discrepancy_notification,
)


@pytest.fixture(autouse=True)
def admin_email(settings):
    """Set up admin email for testing."""
    settings.ADMINS = [("Name", "admin@email.com")]


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


message = Template(
    "The following discrepancies for $source allocations were detected between "
    "Coldfront and Active Directory:"
    "\n\n"
    "$membership_discrepancies_text"
    "$missing_ldap_groups_text"
)


@pytest.mark.parametrize("source", ["RDF", "HX2"])
def test_send_discrepancy_notification_membership_discrepancies(source: str):
    """Test email text for group membership discrepancies."""
    check_result = DiscrepancyCheckResult(
        membership_discrepancies=[
            Discrepancy(
                project_name="Test Project",
                group_name="rdfdev-testgroup",
                missing_members=["alice"],
                extra_members=["bob"],
            )
        ],
        missing_ldap_groups=[],
    )

    membership_discrepancies_text = (
        "Membership Discrepancies:\n\n"
        "- Project: Test Project (Group: rdfdev-testgroup)\n"
        "  Missing members (in Coldfront but not in AD):\n"
        "    - alice\n"
        "  Extra members (in AD but not in Coldfront):\n"
        "    - bob\n"
    )

    send_discrepancy_notification(check_result, source=source)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].body == message.substitute(
        source=source,
        membership_discrepancies_text=membership_discrepancies_text,
        missing_ldap_groups_text="",
    )


@pytest.mark.parametrize("source", ["RDF", "HX2"])
def test_send_discrepancy_notification_missing_ldap_groups(source: str):
    """Test that the discrepancy email includes missing LDAP groups."""
    check_result = DiscrepancyCheckResult(
        membership_discrepancies=[],
        missing_ldap_groups=["rdfdev-testgroup"],
    )
    missing_ldap_groups_text = (
        f"\n{source} allocations that do not have corresponding AD group:\n"
        "\t- rdfdev-testgroup\n"
    )

    send_discrepancy_notification(check_result, source=source)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].body == message.substitute(
        source=source,
        membership_discrepancies_text="",
        missing_ldap_groups_text=missing_ldap_groups_text,
    )


@override_settings(RCS_NOTIFICATION_EMAILS=[("Name", "rcs@email.com")])
def test_notify_platforms_to_manually_delete_allocation():
    """Test the notify platforms to manually delete allocation email."""
    shortname = "bio-research-01"
    allocation_id = 12345

    expected_subject = (
        "Manual Deletion Required for RDF Allocation - bio-research-01 (ID: 12345)"
    )

    expected_message = """
    The RDF allocation 'bio-research-01' with ID 12345
    has reached the 'Deleted' status.
    Please take the necessary steps to manually delete all associated data
    for this allocation.
    """

    notify_platforms_to_manually_delete_allocation(shortname, allocation_id)

    # Django intercepts emails sent during tests, access them using mail.
    assert len(mail.outbox) == 1
    actual_message = mail.outbox[0].body
    actual_subject = mail.outbox[0].subject

    assert actual_subject == expected_subject
    assert actual_message == textwrap.dedent(expected_message)


def test_send_hx2_accessaccess_group_discrepancy_notification():
    """Test sending discrepancy notification for HX2 access groups."""
    check_result = Discrepancy(
        project_name="",
        group_name="hx2-testgroup",
        missing_members=["alice"],
        extra_members=["bob"],
    )

    expected_body = (
        "A discrepancy has been detected between the membership of the HX2 access group"
        " in Active Directory (hx2-testgroup) and the expected membership based on "
        "Coldfront data.\n\n"
        "Missing members (in Coldfront but not in AD):\n"
        "  - alice\n\n"
        "Extra members (in AD but not in Coldfront):\n"
        "  - bob\n"
    )
    send_hx2_access_group_discrepancy_notification(check_result)
    (message,) = mail.outbox
    assert message.subject.endswith(
        "Coldfront - HX2 Access Group Membership Discrepancy Detected"
    )
    assert message.body == expected_body.lstrip()
