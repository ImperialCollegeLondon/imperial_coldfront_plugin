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
    if any(
        [
            user_profile["user_type"] != "Member",
            user_profile["record_status"] != "Live",
            not _filter_entity_type(user_profile["entity_type"]),
            None
            in [
                user_profile["email"],
                user_profile["name"],
                user_profile["department"],
            ],
        ]
    ):
        return False
    return True
