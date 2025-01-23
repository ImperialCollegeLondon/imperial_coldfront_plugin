"""Plugin Django models."""

from django.conf import settings
from django.db import models


class ResearchGroup(models.Model):
    """Represents a research group.

    This model stores information about research groups, including their owner,
    a unique group ID (gid), and the group name.

    Attributes:
        owner (ForeignKey): A reference to the user designated as the group's owner,
            connected to AUTH_USER_MODEL. Deletes related groups when the owner
            is deleted.
        gid (IntegerField): A unique identifier for the group.
        name (CharField): The name of the research group with a maximum length
            of 255 characters.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    gid = models.IntegerField()
    name = models.CharField(max_length=255)


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
        is_manager (BooleanField): A boolean value indicating if a member is a manager.
        expiration (DateTimeField): The date and time when the membership expires.
    """

    group = models.ForeignKey(
        ResearchGroup,
        on_delete=models.CASCADE,
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    is_manager = models.BooleanField(default=False)
    expiration = models.DateTimeField(null=True, blank=True)


class UnixUID(models.Model):
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
    )
    identifier = models.IntegerField()
