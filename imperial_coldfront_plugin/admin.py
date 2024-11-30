"""Django admin configuration."""

from django.contrib import admin

from .models import GroupMembership


class GroupMembershipAdmin(admin.ModelAdmin):
    """Admin configuration for the GroupMembership model."""

    pass


admin.site.register(GroupMembership, GroupMembershipAdmin)
