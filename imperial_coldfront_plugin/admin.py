"""Django admin configuration."""

from django.contrib import admin

from .models import CreditTransaction


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin[CreditTransaction]):
    """Admin configuration for CreditTransaction model."""

    list_display = ("authoriser", "project", "timestamp", "amount", "description")
