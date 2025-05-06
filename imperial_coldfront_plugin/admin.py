"""Django admin configuration."""

from django.contrib import admin

from .models import GroupMembership, ResearchGroup


@admin.register(ResearchGroup)
class ResearchGroupAdmin(admin.ModelAdmin):
    """Admin configuration for the ResearchGroup model."""

    list_display = ("owner", "gid", "name")


@admin.register(GroupMembership)
class GroupMembershipAdmin(admin.ModelAdmin):
    """Admin configuration for the GroupMembership model."""

    pass
