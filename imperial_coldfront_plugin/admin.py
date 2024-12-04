"""Django admin configuration."""

from django.contrib import admin

from .models import GroupMembership, ResearchGroup


class ResearchGroupAdmin(admin.ModelAdmin):
    """Admin configuration for the ResearchGroup model."""

    pass


admin.site.register(ResearchGroup, ResearchGroupAdmin)


class GroupMembershipAdmin(admin.ModelAdmin):
    """Admin configuration for the GroupMembership model."""

    pass


admin.site.register(GroupMembership, GroupMembershipAdmin)
