"""Plugin Django models."""

import typing

from coldfront.core.allocation.models import Allocation, AllocationAttribute
from coldfront.core.project.models import Project, ProjectAttribute
from django.conf import settings
from django.db import models


class RDFAllocation(Allocation):
    """Proxy model for RDF Active allocations."""

    class Meta:
        """Meta class for RDFAllocation."""

        proxy = True

    def clean(self) -> None:
        """Clean and validate RDFAllocation."""
        super().clean()
        resource = self.get_parent_resource
        if not resource or resource.name != "RDF Active":
            raise ValueError(
                "RDFAllocation must be associated with the 'RDF Active' resource"
            )

    @classmethod
    def from_allocation(cls, allocation: Allocation) -> typing.Self:
        """Create an RDFAllocation instance from a base Allocation instance."""
        return cls(
            pk=allocation.pk,
            project=allocation.project,
            status=allocation.status,
            quantity=allocation.quantity,
            start_date=allocation.start_date,
            end_date=allocation.end_date,
            justification=allocation.justification,
            description=allocation.description,
            is_locked=allocation.is_locked,
            is_changeable=allocation.is_changeable,
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
            raise ValueError(
                f"{attribute_name} attribute not found for allocation - {self}"
            )

    @property
    def shortname_attr(self) -> AllocationAttribute:
        """Get the shortname attribute of the allocation."""
        return self._get_attribute("Shortname")

    @property
    def shortname(self) -> str:
        """Get the shortname of the allocation."""
        value = self.shortname_attr.typed_value()
        if not isinstance(value, str):
            raise ValueError(f"Expected shortname to be a string, got {type(value)}")
        return value

    @property
    def ldap_shortname(self) -> str:
        """Get the shortname of the allocation, with the LDAP prefix appended."""
        return f"{settings.LDAP_SHORTNAME_PREFIX}{self.shortname}"

    @property
    def storage_quota_tb_attr(self) -> AllocationAttribute:
        """Get the shortname attribute of the allocation."""
        return self._get_attribute("Storage Quota (TB)")

    @property
    def storage_quota_tb(self) -> int:
        """Get the shortname of the allocation."""
        value = self.storage_quota_tb_attr.typed_value()
        if not isinstance(value, int):
            raise ValueError(
                f"Expected storage quota to be an integer, got {type(value)}"
            )
        return value

    @property
    def files_quota_attr(self) -> AllocationAttribute:
        """Get the shortname attribute of the allocation."""
        return self._get_attribute("Files Quota")

    @property
    def files_quota(self) -> int:
        """Get the shortname of the allocation."""
        value = self.files_quota_attr.typed_value()
        if not isinstance(value, int):
            raise ValueError(
                f"Expected files quota to be an integer, got {type(value)}"
            )
        return value


class ICLProject(Project):
    """Proxy model for RDF Projects."""

    class Meta:
        """Meta class for ICLProject."""

        proxy = True

    def _get_attribute(self, attribute_name: str) -> ProjectAttribute:
        try:
            return self.projectattribute_set.get(proj_attr_type__name=attribute_name)
        except ProjectAttribute.MultipleObjectsReturned:
            raise ValueError(
                f"Multiple {attribute_name} attributes found for project - {self}"
            )
        except (ProjectAttribute.DoesNotExist, AttributeError):
            raise ValueError(
                f"{attribute_name} attribute not found for project - {self}"
            )

    @property
    def group_id(self) -> str:
        """Get the group ID attribute of the project."""
        return self._get_attribute("Group ID").value

    @property
    def faculty(self) -> str:
        """Get the faculty of the project."""
        return self._get_attribute("Faculty").value

    @property
    def department(self) -> str:
        """Get the department of the project."""
        return self._get_attribute("Department").value

    @property
    def ask_ticket_reference_attr(self) -> ProjectAttribute:
        """Get the Ask Ticket Reference attribute of the project."""
        return self._get_attribute("ASK Ticket Reference")


class CreditTransaction(models.Model):
    """Model representing a credit transaction."""

    timestamp = models.DateTimeField(auto_now_add=True)
    amount = models.IntegerField()
    description = models.CharField(max_length=255)
    project = models.ForeignKey(ICLProject, on_delete=models.CASCADE)

    def __str__(self) -> str:
        """String representation of the CreditTransaction."""
        return f"CreditTransaction(id={self.id}, project={self.project.title})"
