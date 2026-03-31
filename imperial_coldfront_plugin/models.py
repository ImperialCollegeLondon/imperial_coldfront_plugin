"""Plugin Django models."""

import typing
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
    AllocationStatusChoice,
    AllocationUser,
    AllocationUserStatusChoice,
)
from coldfront.core.project.models import (
    Project,
    ProjectAttribute,
    ProjectAttributeType,
    ProjectStatusChoice,
    ProjectUser,
    ProjectUserRoleChoice,
    ProjectUserStatusChoice,
)
from coldfront.core.resource.models import Resource
from django.conf import settings
from django.db import models, transaction

from imperial_coldfront_plugin.gid import get_new_gid
from imperial_coldfront_plugin.ldap import ldap_create_group

if TYPE_CHECKING:
    from django.contrib.auth.models import User as UserType


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


class HX2AllocationManager(models.Manager["HX2Allocation"]):
    """Manager for HX2 Allocations."""

    def create_hx2allocation(
        self,
        *,
        project: Project,
        status: AllocationStatusChoice,
        quantity: int,
        start_date: date,
        end_date: date,
        justification: str,
        description: str,
        is_locked: bool,
        is_changeable: bool,
    ) -> "HX2Allocation":
        """Create a new HX2Allocation from validated data."""
        with transaction.atomic():
            allocation_obj = self.model(
                project=project,
                status=status,
                quantity=quantity,
                start_date=start_date,
                end_date=end_date,
                justification=justification,
                description=description,
                is_locked=is_locked,
                is_changeable=is_changeable,
            )
            allocation_obj.save()

            hx2_resource = Resource.objects.get(name="HX2")
            allocation_obj.resources.add(hx2_resource)

            gid = get_new_gid()
            gid_attribute_type = AllocationAttributeType.objects.get(name="GID")
            AllocationAttribute.objects.create(
                allocation=allocation_obj,
                allocation_attribute_type=gid_attribute_type,
                value=gid,
            )

            if settings.LDAP_ENABLED:
                ldap_create_group(group_name=allocation_obj.ldap_shortname, gid=gid)

            active_status = AllocationUserStatusChoice.objects.get(name="Active")
            AllocationUser.objects.create(
                allocation=allocation_obj,
                user=project.pi,
                status=active_status,
            )
            return allocation_obj


class HX2Allocation(Allocation):
    """Proxy model for HX2 RDF Active allocations."""

    objects = HX2AllocationManager()

    class Meta:
        """Meta class for HX2Allocation."""

        proxy = True

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialise HX2Allocation and validate resource association."""
        super().__init__(*args, **kwargs)
        if self.pk:
            # Only validate resource association for existing allocations, as new
            # allocations may not have a resource assigned yet.
            resource = self.get_parent_resource
            if not resource or resource.name != "HX2":
                raise ValueError(
                    "HX2Allocation must be associated with the 'HX2' resource"
                )

    def __str__(self) -> str:
        """String representation of HX2Allocation."""
        # This is an override from the base Allocation to avoid including the resource.
        # For further explanation see __str__ method of RDFAllocation.
        return f"HX2Allocation(id={self.pk}, project={self.project.title})"

    @classmethod
    def from_allocation(cls, allocation: Allocation) -> typing.Self:
        """Create an HX2Allocation instance from a base Allocation instance."""
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

    @property
    def shortname(self) -> str:
        """Get the shortname attribute of the allocation, which is based on Group ID."""
        try:
            value = self.project.projectattribute_set.get(
                proj_attr_type__name="Group ID"
            ).value
        except ProjectAttribute.MultipleObjectsReturned:
            raise ValueError(
                f"Multiple Group ID attributes found for allocation - {self}"
            )
        except (ProjectAttribute.DoesNotExist, AttributeError):
            raise ValueError(f"Group ID attribute not found for allocation - {self}")

        if not isinstance(value, str):
            raise ValueError(f"Expected shortname to be a string, got {type(value)}")
        return value

    @property
    def ldap_shortname(self) -> str:
        """Get the shortname of the allocation, with the LDAP prefix appended."""
        return f"{settings.LDAP_SHORTNAME_PREFIX}{self.shortname}"


class ICLProjectManager(models.Manager["ICLProject"]):
    """Manager for RDF projects."""

    def create_iclproject(
        self,
        *,
        title: str,
        description: str,
        field_of_science: object,
        user: "UserType",
        faculty: str,
        department: str,
        group_id: str,
        ticket_id: str = "",
    ) -> "ICLProject":
        """Create a new ICL project from validated data."""
        project_obj = self.model(
            title=title,
            description=description,
            field_of_science=field_of_science,
            status=ProjectStatusChoice.objects.get(name="Active"),
            pi=user,
        )
        project_obj.save()
        ProjectUser.objects.create(
            user=user,
            project=project_obj,
            role=ProjectUserRoleChoice.objects.get(name="Manager"),
            status=ProjectUserStatusChoice.objects.get(name="Active"),
        )
        group_id_attribute_type = ProjectAttributeType.objects.get(name="Group ID")
        location_attribute_type = ProjectAttributeType.objects.get(
            name="Filesystem location"
        )
        department_attribute_type = ProjectAttributeType.objects.get(name="Department")
        faculty_attribute_type = ProjectAttributeType.objects.get(name="Faculty")
        ProjectAttribute.objects.create(
            proj_attr_type=department_attribute_type,
            project=project_obj,
            value=department,
        )
        ProjectAttribute.objects.create(
            proj_attr_type=faculty_attribute_type,
            project=project_obj,
            value=faculty,
        )
        ProjectAttribute.objects.create(
            proj_attr_type=group_id_attribute_type,
            project=project_obj,
            value=group_id,
        )
        ProjectAttribute.objects.create(
            proj_attr_type=location_attribute_type,
            project=project_obj,
            value=str(
                Path(
                    settings.GPFS_FILESYSTEM_MOUNT_PATH,
                    settings.GPFS_FILESYSTEM_NAME,
                    settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES,
                    faculty,
                    department,
                    group_id,
                )
            ),
        )
        if ticket_id:
            ticket_attribute_type = ProjectAttributeType.objects.get(
                name="ASK Ticket Reference"
            )
            ProjectAttribute.objects.create(
                proj_attr_type=ticket_attribute_type,
                project=project_obj,
                value=ticket_id,
            )

        return project_obj


class ICLProject(Project):
    """Proxy model for RDF Projects."""

    objects = ICLProjectManager()

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
    authoriser = models.CharField(max_length=255, default="")
    project = models.ForeignKey(ICLProject, on_delete=models.CASCADE)

    def __str__(self) -> str:
        """String representation of the CreditTransaction."""
        return f"CreditTransaction(id={self.id}, project={self.project.title})"
