"""Plugin Django models."""

from django.conf import settings
from django.db import models


class GroupMember(models.Model):
    """Membership relationship within a group, associating an owner with a member.

    This model stores relationships where each instance represents an ownership
    connection between two users within a group, where `owner` is the user who
    owns the membership (or perhaps manages the group) and `member` is the
    associated user.

    Attributes:
        owner (ForeignKey): A reference to the user designated as owner, connected to
            AUTH_USER_MODEL. Deletes related memberships when the owner is deleted.
        member (ForeignKey): A reference to the user designated as member, connected to
            AUTH_USER_MODEL. Deletes related memberships when the member is deleted.
    """

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
