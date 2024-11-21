"""Plugin Django models."""

from django.conf import settings
from django.db import models


class GroupMembership(models.Model):
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

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_group_memberships_set",
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="group_memberships_set",
    )


class UserID(models.Model):
    """Identity data to map a user to a unique identifier.

    This model stores a unique identifier for each user, which can be used to
    identify users in external systems. The identifier is an integer value that
    is unique to each user user.

    Attributes:
        user (OneToOneField): A reference to the user, connected to AUTH_USER_MODEL.
            Deletes the related identifier when the user is deleted.
        identifier (IntegerField): A unique identifier for the user.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_id",
    )
    identifier = models.IntegerField(default=0)
