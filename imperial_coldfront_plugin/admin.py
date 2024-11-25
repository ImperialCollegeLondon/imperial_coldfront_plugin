"""Django admin configuration."""

from django.contrib import admin

from .models import GroupMembership


class GroupMembershipAdmin(admin.ModelAdmin):
    pass


admin.site.register(GroupMembership, GroupMembershipAdmin)