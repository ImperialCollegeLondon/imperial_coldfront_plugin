from pathlib import Path

import pytest
from coldfront.core.allocation.models import Allocation, AllocationStatusChoice
from coldfront.core.project.models import ProjectAttribute, ProjectAttributeType
from django.utils import timezone

from imperial_coldfront_plugin.models import HX2Allocation


class TestCreditTransaction:
    """Tests for the CreditTransaction model."""

    def test_model_str(self, project):
        """Test the object string for the CreditTransaction model."""
        from imperial_coldfront_plugin import models

        transaction = models.CreditTransaction(
            id=123,
            project=project,
            amount=1000,
            description="Test transaction",
        )
        assert str(transaction) == f"CreditTransaction(id=123, project={project.title})"

    def test_timestamp_auto_now_add(self):
        """Test that timestamp is automatically set on creation."""
        from imperial_coldfront_plugin import models

        field = models.CreditTransaction._meta.get_field("timestamp")
        assert field.auto_now_add is True

    def test_amount_field(self):
        """Test the amount field configuration."""
        from django.db import models as dj_models

        from imperial_coldfront_plugin import models

        field = models.CreditTransaction._meta.get_field("amount")
        assert isinstance(field, dj_models.IntegerField)

    def test_description_field(self):
        """Test the description field configuration."""
        from django.db import models as dj_models

        from imperial_coldfront_plugin import models

        field = models.CreditTransaction._meta.get_field("description")
        assert isinstance(field, dj_models.CharField)
        assert field.max_length == 255

    def test_project_foreign_key(self):
        """Test the project foreign key configuration."""
        from imperial_coldfront_plugin import models
        from imperial_coldfront_plugin.models import ICLProject

        field = models.CreditTransaction._meta.get_field("project")
        assert field.remote_field is not None
        assert field.remote_field.model is ICLProject
        assert field.remote_field.on_delete.__name__ == "CASCADE"

    @pytest.mark.parametrize(
        ["amount", "description"],
        [
            [1000, "Credit addition"],
            [-500, "Credit deduction"],
            [0, "No change"],
        ],
    )
    def test_create_transaction(self, project, amount, description):
        """Test creating credit transactions with different amounts."""
        from imperial_coldfront_plugin import models

        transaction = models.CreditTransaction(
            project=project,
            amount=amount,
            description=description,
        )
        assert transaction.amount == amount
        assert transaction.description == description
        assert transaction.project == project


class TestRDFAllocation:
    """Tests for the RDFAllocation model."""

    def test_shortname(self, rdf_allocation):
        """Test that shortname_attr returns the correct attribute."""
        assert rdf_allocation.shortname_attr.value == "shorty"
        assert rdf_allocation.shortname == "shorty"

    def test_storage_quota_tb_attr(self, rdf_allocation):
        """Test that storage_quota_tb_attr returns the correct attribute."""
        from coldfront.core.allocation.models import (
            AllocationAttribute,
            AllocationAttributeType,
        )

        attr_type = AllocationAttributeType.objects.get(name="Storage Quota (TB)")
        AllocationAttribute.objects.create(
            allocation_attribute_type=attr_type, allocation=rdf_allocation, value=10
        )

        assert rdf_allocation.storage_quota_tb_attr.value == "10"
        assert rdf_allocation.storage_quota_tb == 10

    def test_files_quota_attr(self, rdf_allocation):
        """Test that files_quota_attr returns the correct attribute."""
        from coldfront.core.allocation.models import (
            AllocationAttribute,
            AllocationAttributeType,
        )

        attr_type = AllocationAttributeType.objects.get(name="Files Quota")
        AllocationAttribute.objects.create(
            allocation_attribute_type=attr_type, allocation=rdf_allocation, value=1000
        )

        assert rdf_allocation.files_quota_attr.value == "1000"
        assert rdf_allocation.files_quota == 1000

    def test_shortname_missing(self, rdf_allocation):
        """Test that ValueError is raised when Shortname attribute is missing."""
        rdf_allocation.shortname_attr.delete()

        with pytest.raises(ValueError, match="Shortname attribute not found"):
            rdf_allocation.shortname

    def test_storage_quota_tb_missing(self, rdf_allocation):
        """Test that error is raised when Storage Quota (TB) attribute is missing."""
        with pytest.raises(
            ValueError, match="Storage Quota \(TB\) attribute not found"
        ):
            rdf_allocation.storage_quota_tb

    def test_files_quota_missing(self, rdf_allocation):
        """Test that ValueError is raised when Files Quota attribute is missing."""
        with pytest.raises(ValueError, match="Files Quota attribute not found"):
            rdf_allocation.files_quota

    def test_storage_quota_tb_bad_value(self, rdf_allocation):
        """Test that error is thrown when Storage Quota (TB) has a non-integer value."""
        from coldfront.core.allocation.models import (
            AllocationAttribute,
            AllocationAttributeType,
        )

        attr_type = AllocationAttributeType.objects.get(name="Storage Quota (TB)")
        AllocationAttribute.objects.create(
            allocation_attribute_type=attr_type,
            allocation=rdf_allocation,
            value="not_an_int",
        )
        with pytest.raises(ValueError):
            rdf_allocation.storage_quota_tb


class TestICLProject:
    """Tests for the ICLProject model."""

    def test_create_iclproject(self, user, settings):
        """Test that the manager creates the project, membership, and attributes."""
        from coldfront.core.field_of_science.models import FieldOfScience
        from coldfront.core.project.models import (
            ProjectAttributeType,
            ProjectStatusChoice,
            ProjectUserRoleChoice,
            ProjectUserStatusChoice,
        )

        from imperial_coldfront_plugin.models import ICLProject

        ProjectStatusChoice.objects.create(name="Active")
        project_user_status = ProjectUserStatusChoice.objects.create(name="Active")
        project_user_role = ProjectUserRoleChoice.objects.create(name="Manager")
        field_of_science = FieldOfScience.objects.create(pk=FieldOfScience.DEFAULT_PK)

        settings.GPFS_FILESYSTEM_NAME = "fsname"
        settings.GPFS_FILESYSTEM_MOUNT_PATH = "/mountpath"
        settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES = "top/level"

        faculty = "foe"
        department = "dsde"
        title = "group title"
        description = "group_description"
        ticket_id = "RQST3939393"

        project = ICLProject.objects.create_iclproject(
            title=title,
            description=description,
            field_of_science=field_of_science,
            user=user,
            faculty=faculty,
            department=department,
            group_id=user.username,
            ticket_id=ticket_id,
        )

        assert project.title == title
        assert project.pi == user
        assert project.description == description

        project_user = project.projectuser_set.get()
        assert project_user.status == project_user_status
        assert project_user.role == project_user_role

        assert project.faculty == faculty
        assert project.department == department
        assert project.group_id == user.username

        project.projectattribute_set.get(
            proj_attr_type__name="Filesystem location",
            value=str(
                Path(
                    settings.GPFS_FILESYSTEM_MOUNT_PATH,
                    settings.GPFS_FILESYSTEM_NAME,
                    settings.GPFS_FILESYSTEM_TOP_LEVEL_DIRECTORIES,
                    faculty,
                    department,
                    user.username,
                )
            ),
        )

        ticket_attribute_type = ProjectAttributeType.objects.get(
            name="ASK Ticket Reference"
        )
        project.projectattribute_set.get(
            proj_attr_type=ticket_attribute_type,
            value=ticket_id,
        )

    def test_group_id(self, project):
        """Test that group_id returns the correct value."""
        assert project.group_id == "testuser"

    def test_faculty(self, project):
        """Test that faculty returns the correct value."""
        assert project.faculty == "foe"

    def test_department(self, project):
        """Test that department returns the correct value."""
        assert project.department == "dsde"

    def test_ask_ticket_reference_attr(self, project):
        """Test that ask_ticket_reference_attr returns the correct attribute."""
        from coldfront.core.project.models import ProjectAttribute, ProjectAttributeType

        attr_type = ProjectAttributeType.objects.get(name="ASK Ticket Reference")
        ProjectAttribute.objects.create(
            proj_attr_type=attr_type, project=project, value="Ref123"
        )

        assert project.ask_ticket_reference_attr.value == "Ref123"

    def test_group_id_missing(self, project):
        """Test that ValueError is raised when Group ID attribute is missing."""
        project.projectattribute_set.filter(proj_attr_type__name="Group ID").delete()

        with pytest.raises(ValueError, match="Group ID attribute not found"):
            project.group_id

    def test_faculty_missing(self, project):
        """Test that ValueError is raised when Faculty attribute is missing."""
        project.projectattribute_set.filter(proj_attr_type__name="Faculty").delete()

        with pytest.raises(ValueError, match="Faculty attribute not found"):
            project.faculty

    def test_department_missing(self, project):
        """Test that ValueError is raised when Department attribute is missing."""
        project.projectattribute_set.filter(proj_attr_type__name="Department").delete()

        with pytest.raises(ValueError, match="Department attribute not found"):
            project.department

    def test_ask_ticket_reference_attr_missing(self, project):
        """Test that error is raised when ASK Ticket Reference attribute is missing."""
        with pytest.raises(
            ValueError, match="ASK Ticket Reference attribute not found"
        ):
            project.ask_ticket_reference_attr


class TestHX2Allocation:
    """Tests for the HX2Allocation model."""

    def test_init_new_allocation(self, project):
        """Test a new HX2Allocation can be initialised without a HX2 Resource."""
        active_status, _ = AllocationStatusChoice.objects.get_or_create(name="Active")
        # Should not raise an error:
        HX2Allocation(
            project=project,
            status=active_status,
            start_date=timezone.now(),
            end_date=timezone.now(),
        )

    def test_create(self, project):
        """Test that HX2Allocation can be created without a HX2 resource."""
        active_status, _ = AllocationStatusChoice.objects.get_or_create(name="Active")
        HX2Allocation.objects.create(
            project=project,
            status=active_status,
            start_date=timezone.now(),
            end_date=timezone.now(),
        )

    def test_init_for_saved_non_hx2_allocation(self, project):
        """Test initialising HX2Allocation with non-HX2 Allocation raises error."""
        active_status, _ = AllocationStatusChoice.objects.get_or_create(name="Active")

        # create a non-RDF allocation
        allocation = Allocation.objects.create(
            project=project,
            status=active_status,
            start_date=timezone.now(),
            end_date=timezone.now(),
        )

        with pytest.raises(ValueError):
            HX2Allocation.objects.get(pk=allocation.pk)

        with pytest.raises(ValueError):
            HX2Allocation.from_allocation(allocation)

    def test_shortname(self, hx2_allocation, hx2_allocation_group_id):
        """Test that shortname returns the correct value."""
        assert hx2_allocation.shortname == hx2_allocation_group_id

    def test_shortname_missing(self, project, hx2_allocation):
        """Test that ValueError is raised when Shortname attribute is missing."""
        ProjectAttribute.objects.filter(
            project=project,
            proj_attr_type__name="Group ID",
        ).delete()

        with pytest.raises(ValueError, match="Group ID attribute not found"):
            hx2_allocation.shortname

    def test_shortname_multiple(self, project, hx2_allocation):
        """Test that ValueError is raised when multiple Shortname attributes exist."""
        attr_type = ProjectAttributeType.objects.get(name="Group ID")
        ProjectAttribute.objects.create(
            proj_attr_type=attr_type,
            project=project,
            value="duplicate-short",
        )

        with pytest.raises(ValueError, match="Multiple Group ID attributes"):
            hx2_allocation.shortname

    def test_ldap_shortname(self, hx2_allocation, hx2_allocation_group_id, settings):
        """Test that ldap_shortname returns shortname with LDAP prefix."""
        settings.LDAP_SHORTNAME_PREFIX = "ldap-"
        assert hx2_allocation.ldap_shortname == f"ldap-{hx2_allocation_group_id}"

    def test_ldap_shortname_empty_prefix(
        self, hx2_allocation, hx2_allocation_group_id, settings
    ):
        """Test that ldap_shortname works with an empty prefix."""
        settings.LDAP_SHORTNAME_PREFIX = ""
        assert hx2_allocation.ldap_shortname == hx2_allocation_group_id
