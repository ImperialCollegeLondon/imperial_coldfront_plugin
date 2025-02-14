"""Policy functionality governing the eligibility of users access RCS systems."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .models import GroupMembership, ResearchGroup


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


def user_already_has_hpc_access(username):
    """Check if the user is already a member of a ResearchGroup."""
    User = get_user_model()
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return False
    return (
        user.is_superuser
        or GroupMembership.objects.filter(member=user).exists()
        or ResearchGroup.objects.filter(owner=user).exists()
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


def check_group_owner_manager_or_superuser(group, user):
    """Check if the user is the owner or manager of the group or a superuser."""
    if not (
        group.owner == user
        or user.is_superuser
        or GroupMembership.objects.filter(
            group=group, member=user, is_manager=True, expiration__gt=timezone.now()
        ).exists()
    ):
        raise PermissionDenied


def check_group_owner_or_superuser(group, user):
    """Check if the user is the owner of the group or a superuser."""
    if not (group.owner == user or user.is_superuser):
        raise PermissionDenied
