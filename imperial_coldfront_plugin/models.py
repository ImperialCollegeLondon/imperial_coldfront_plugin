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

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize RDFAllocation and validate resource association."""
        super().__init__(*args, **kwargs)
        if self.pk:
            # Only validate resource association for existing allocations, as new
            # allocations may not have a resource assigned yet. This allows for
            # RDFAllocations to be created and then have the resource assigned
            # afterwards without raising an error.
            resource = self.get_parent_resource
            if not resource or resource.name != "RDF Active":
                raise ValueError(
                    "RDFAllocation must be associated with the 'RDF Active' resource"
                )

    def __str__(self) -> str:
        """String representation of the RDFAllocation."""
        # this is overridden from the base Allocation to avoid including the resource in
        # the string representation, as if an instance does not have a resource assigned
        # this leads to errors when trying to print them. Without this override it's
        # difficult to get any clean backtraces for error handling as they often involve
        # printing the allocation which then raises an error due to the missing
        # resource, which is often a symptom of the underlying issue rather than the
        # root cause. By removing the resource from the string representation we can
        # avoid these issues and get clearer error messages that point to the actual
        # problem. V. annoying!!!
        return f"RDFAllocation(id={self.pk}, project={self.project.title})"

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
