"""Plugin views."""

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from .models import GroupMembership

User = get_user_model()


@login_required
def group_members_view(request: HttpRequest, user_pk: int) -> HttpResponse:
    """Display the members of a research group for a specific user.

    This view retrieves and displays all members associated with a research group
    where the specified user (identified by `user_pk`) is the owner. Access is
    restricted to either the group owner or an administrator. Unauthorised users will
    receive a permission denied response.

    The view also checks if the specified user has Principal Investigator (PI) status
    (via the `is_pi` attribute). If the user is not a PI, the view will render a
    message indicating that the user does not own a group.

    Args:
        request (HttpRequest): The HTTP request object containing metadata about the
            request.
        user_pk (int): The primary key of the user who owns the research group to be
            displayed.

    Returns:
        HttpResponse: If access is permitted, renders `group_members.html`
                      displaying the group members.
                      If the logged-in user is unauthorised, returns a
                      `HttpResponseForbidden`.
                      If the user is not a PI, renders `no_group.html` with an
                      appropriate message.

    Raises:
        Http404: If no user is found with the provided `user_pk`.
    """
    user = get_object_or_404(User, pk=user_pk)

    if request.user != user and not request.user.is_superuser:
        return HttpResponseForbidden("Permission denied")

    if not user.userprofile.is_pi:
        return render(request, "no_group.html", {"message": "You do not own a group."})

    group_members = GroupMembership.objects.filter(group__owner=user)

    return render(request, "group_members.html", {"group_members": group_members})


@login_required
def check_access(request: HttpRequest):
    """Informational view displaying the user's current access to RCS resources."""
    if request.user.userprofile.is_pi:
        message = "You have access to RCS resources as a PI."
    elif request.user.is_superuser:
        message = "You have access to RCS resources as an administrator."
    else:
        try:
            group_membership = GroupMembership.objects.get(member=request.user)
            message = (
                "You have been granted access to the RCS compute cluster as a member "
                "of the research group of "
                f"{group_membership.group.owner.get_full_name()}."
            )
        except GroupMembership.DoesNotExist:
            message = "You do not currently have access to the RCS compute cluster."

    return render(
        request, "imperial_coldfront_plugin/check_access.html", dict(message=message)
    )
