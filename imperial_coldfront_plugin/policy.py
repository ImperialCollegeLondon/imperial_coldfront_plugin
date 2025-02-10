"""Policy functionality governing the eligibility of users access RCS systems."""


def _filter_entity_type(entity_type):
    """Capture complex sublogic for filtering entity types."""
    if entity_type is None:
        return False
    if "Room" in entity_type or entity_type == "Shared Mailbox":
        return False
    return True


def user_eligible_for_hpc_access(user_profile):
    """Assess the eligibility of a user to join a ResearchGroup.

    Imperial identity systems contain entries for non-human entities such as rooms and
    shared mailboxes that should be removed from consideration.
    """
    return all(
        [
            user_profile["user_type"] == "Member",
            user_profile["record_status"] == "Live",
            _filter_entity_type(user_profile["entity_type"]),
            None
            not in (
                user_profile["email"],
                user_profile["name"],
                user_profile["department"],
            ),
        ]
    )


PI_DISALLOWED_DEPARTMENTS = [
    "External Users",
    "Reach Out",
    "Catering Services",
    "Careers Service",
    "Early Years Education Centre",
    "CONTRACTOR",
    "NONE",
    "Campus Services",
    "Guest Access",
    "Union",
    "Registry",
    "Residential Services",
    "Estates Division",
]
PI_ALLOWED_TITLES = ["Fellow", "Lecturer", "Chair", "Professor", "Reader", "Director"]
PI_DISALLOWED_TITLE_QUALIFIERS = ["Visiting", "Emeritus", "Honorary"]


def user_eligible_to_be_pi(user_profile):
    """Assess eligibilty of a user be a Principal Investigator."""
    job_title = user_profile["job_title"]
    if any(
        (
            user_profile["record_status"] != "Live",
            user_profile["department"] in PI_DISALLOWED_DEPARTMENTS,
            user_profile["entity_type"] not in ["Staff", "Employee"],
            not job_title,
        )
    ):
        return False

    if not any(role in job_title for role in PI_ALLOWED_TITLES):
        return False

    if any(qualifier in job_title for qualifier in PI_DISALLOWED_TITLE_QUALIFIERS):
        return False

    return True
