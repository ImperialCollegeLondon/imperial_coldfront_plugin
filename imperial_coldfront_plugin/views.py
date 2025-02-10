"""Plugin views."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import ResearchGroupForm
from .models import GroupMembership, ResearchGroup


@login_required
@permission_required(
    "imperial_coldfront_plugin.add_researchgroup", raise_exception=True
)
def research_group_terms_view(request):
    """View for accepting T&Cs and creating a ResearchGroup."""
    if request.method == "POST":
        form = ResearchGroupForm(request.POST)
        if form.is_valid():
            group_name = form.cleaned_data["name"]
            gid = generate_unique_gid()

            ResearchGroup.objects.create(owner=request.user, gid=gid, name=group_name)

            messages.success(request, "Research group created successfully.")
            return redirect(reverse("imperial_coldfront_plugin:group_members"))
    else:
        form = ResearchGroupForm()

    return render(
        request, "imperial_coldfront_plugin/research_group_terms.html", {"form": form}
    )


def generate_unique_gid():
    """Generate a unique GID for the ResearchGroup."""
    last_gid = ResearchGroup.objects.order_by("-gid").first()
    return (last_gid.gid + 1) if last_gid else 1000  # Start at 1000 if no groups exist


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

    group_members = GroupMembership.objects.filter(owner=user)

    return render(request, "group_members.html", {"group_members": group_members})
