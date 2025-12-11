"""Plugin Django models."""

from coldfront.core.project.models import Project
from django.db import models


class CreditTransaction(models.Model):
    """Model representing a credit transaction."""

    timestamp = models.DateTimeField(auto_now_add=True)
    amount = models.IntegerField()
    description = models.CharField(max_length=255)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)

    def __str__(self) -> str:
        """String representation of the CreditTransaction."""
        return f"CreditTransaction(id={self.id}, project={self.project.title})"
