"""Plugin views."""

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from .models import GroupMember

User = get_user_model()


@login_required
def group_members_view(request: HttpRequest, user_pk: int) -> HttpResponse:
    """Display the members of a research group for a specific user.

    This view retrieves and displays all members associated with a research group
    where the specified user (identified by `user_pk`) is the owner. Access is
    restricted to either the group owner or an administrator. Unauthorised users will
    receive a permission denied response.

    The view also checks if the specified user has Principal Investigator (PI) status
    (via the `is_PI` attribute). If the user is not a PI, the view will render a
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

    if request.user != user and not request.user.is_staff:
        return HttpResponseForbidden("Permission denied")

    if not hasattr(user, "is_PI") or not user.is_PI:
        return render(request, "no_group.html", {"message": "You do not own a group."})

    group_members = GroupMember.objects.filter(owner=user)

    return render(request, "group_members.html", {"group_members": group_members})
