"""Django admin configuration."""

from django.contrib import admin

from .models import GroupMembership, ResearchGroup, UnixUID


@admin.register(ResearchGroup)
class ResearchGroupAdmin(admin.ModelAdmin):
    """Admin configuration for the ResearchGroup model."""

    list_display = ("owner", "gid", "name")


@admin.register(GroupMembership)
class GroupMembershipAdmin(admin.ModelAdmin):
    """Admin configuration for the GroupMembership model."""

    pass


@admin.register(UnixUID)
class UnixUIDAdmin(admin.ModelAdmin):
    """Admin configuration for the UnixUID model."""

    list_display = ("identifier", "user")
