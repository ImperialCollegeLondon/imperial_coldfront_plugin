"""Policy functionality governing the eligibility of users access RCS systems."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .models import GroupMembership, ResearchGroup


def user_eligible_for_hpc_access(user_profile):
    """Assess the eligibility of a user to join a ResearchGroup.

    Imperial identity systems contain entries for non-human entities such as rooms and
    shared mailboxes that should be removed from consideration.
    """
    return all(
        [
            user_profile["user_type"] == "Member",
            user_profile["record_status"] == "Live",
            user_profile["entity_type"] in HPC_ACCESS_ALLOWED_ENTITY_TYPE,
            None
            not in (
                user_profile["email"],
                user_profile["name"],
                user_profile["department"],
            ),
            user_profile["department"] not in HPC_ACCESS_DISALLOWED_DEPARTMENTS,
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
HPC_ACCESS_DISALLOWED_DEPARTMENTS = [
    "Registry",
    "ICT System Accounts",
    "Enterprise",
    "Commercial Operations",
    "Residential Services",
    "Strategic Programmes & Change",
    "Finance Division",
    "Student Services",
    "Division of the University Secretary",
    "Sport and Leisure Services",
    "Institute of Extended Learning",
    "Student Union",
    "Advancement",
    "Campus Operations",
    "Capital Projects and Estates Management",
    "Careers Service",
    "Catering and Events",
    "Catering Services",
    "Administration",
    "Chaplaincy",
    "College Headquarters",
    "Commercial and Investment Activities Group",
    "Communications and Public Affairs",
    "Communications Division",
    "Community Safety and Security",
    "Division of the College Secretary",
    "Early Years Education Centre",
    "Endowment",
    "Estates Division",
    "External Users",
    "Guest Access",
    "Health and Safety Services",
    "Human Resources Division",
    "Investment Office",
    "Marketing, Recruitment and Admissions",
    "Office of the Provost",
    "Other - NHS",
    "Outreach",
    "Property Division",
    "Property Operations",
    "Reach Out",
    "Reactor Centre",
    "Residential Services",
    "Risk Management",
    "Safety Department",
    "School of Professional Development",
    "Security Services",
    "Sport and Leisure Services",
    "Strategic Planning Division",
    "Strategic Programmes & Change",
    "Student Recruitment and Outreach",
    "Student Services",
    "Support Services",
    "ThinkSpace",
    "Union",
    "White City Development",
]
HPC_ACCESS_ALLOWED_ENTITY_TYPE = [
    "Employee",
    "Research Postgraduate",
    "Undergraduate",
    "Honorary",
    "Casual & Bursary",
    "Taught Postgraduate",
    "Casual",
    "Visiting Researcher",
    "Academic Visitor (CWK)",
    "Contingent Worker",
    "MRC Employees",
    "Emeritus",
    "Sponsored Researcher",
    "MRC Employees (CWK)",
]


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


def check_project_pi_or_superuser(project, user):
    """Check if the user is the owner of the project or a superuser."""
    if not (user.is_superuser or user == project.pi):
        raise PermissionDenied
