"""Plugin Django models."""

from typing import Any

from coldfront.core.allocation.models import Allocation, AllocationAttribute
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


class RDFAllocation(Allocation):
    """Proxy model for RDF Active allocations."""

    class Meta:
        """Meta class for RDFAllocation."""

        proxy = True

    def clean(self):
        """Clean and validate RDFAllocation."""
        super().clean()
        resource = self.get_parent_resource
        if not resource or resource.name != "RDF Active":
            raise ValueError(
                "RDFAllocation must be associated with the 'RDF Active' resource"
            )

    def _get_attribute(self, attribute_name: str) -> AllocationAttribute:
        try:
            return self.allocationattribute_set.get(
                allocation_attribute_type__name=attribute_name
            )
        except AllocationAttribute.MultipleObjectsReturned:
            raise ValueError(
                f"Multiple {attribute_name} attributes found for allocation - {self}"
            )
        except (AllocationAttribute.DoesNotExist, AttributeError):
            return None

    def _get_attribute_value(self, attribute_name: str) -> Any:
        attr = self._get_attribute(attribute_name)
        return attr.typed_value() if attr else None

    @property
    def shortname(self) -> str:
        """Get the shortname of the allocation."""
        return self._get_attribute_value("Shortname")

    @property
    def shortname_attr(self) -> AllocationAttribute:
        """Get the shortname attribute of the allocation."""
        return self._get_attribute("Shortname")

    @property
    def storage_quota_tb(self) -> str:
        """Get the shortname of the allocation."""
        return self._get_attribute_value("Storage Quota (TB)")

    @property
    def storage_quota_tb_attr(self) -> AllocationAttribute:
        """Get the shortname attribute of the allocation."""
        return self._get_attribute("Storage Quota (TB)")

    @property
    def files_quota(self) -> str:
        """Get the shortname of the allocation."""
        return self._get_attribute_value("Files Quota")

    @property
    def files_quota_attr(self) -> AllocationAttribute:
        """Get the shortname attribute of the allocation."""
        return self._get_attribute("Files Quota")
