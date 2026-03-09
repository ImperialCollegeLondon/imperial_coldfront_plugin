import pytest


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
        from imperial_coldfront_plugin.models import RDFProject

        field = models.CreditTransaction._meta.get_field("project")
        assert field.remote_field is not None
        assert field.remote_field.model is RDFProject
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


class TestRDFProject:
    """Tests for the RDFProject model."""

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
