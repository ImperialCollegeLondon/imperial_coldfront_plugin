"""Policy functionality governing the eligibility of users access RCS systems."""

from typing import TYPE_CHECKING

from coldfront.core.allocation.models import Project
from django.core.exceptions import PermissionDenied

if TYPE_CHECKING:
    from django.contrib.auth.models import User


def user_eligible_for_hpc_access(user_profile: dict[str, str]) -> bool:
    """Assess the eligibility of a user to join a ResearchGroup.

    This function determines which users are displayed in search results when adding a
    user to a Project.

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


def user_eligible_to_be_pi(user_profile: dict[str, str]) -> bool:
    """Assess eligibilty of a user be a Principal Investigator.

    Args:
        user_profile: User profile information

    Returns:
      True if the user is eligible to be a PI, False otherwise.
    """
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


def check_project_pi_or_superuser(project: Project, user: "User") -> None:
    """Check if the user is the owner of the project or a superuser.

    Args:
      project: The project to check against.
      user: The user to check.

    Raises:
      PermissionDenied: If the user is neither the project owner nor a superuser.
    """
    if not (user.is_superuser or user == project.pi):
        raise PermissionDenied
