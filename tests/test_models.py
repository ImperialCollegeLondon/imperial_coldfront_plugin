import datetime
from pathlib import Path

import pytest
from coldfront.core.allocation.models import Allocation
from coldfront.core.project.models import ProjectAttribute
from django.utils import timezone

from imperial_coldfront_plugin.models import (
    CreditTransaction,
    HX2Allocation,
    ICLProject,
    RDFAllocation,
)


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
        field = CreditTransaction._meta.get_field("project")
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

    def test_storage_quota_tb_attr(self, rdf_allocation, allocation_attribute_factory):
        """Test that storage_quota_tb_attr returns the correct attribute."""
        allocation_attribute_factory(
            name="Storage Quota (TB)", allocation=rdf_allocation, value=10
        )

        assert rdf_allocation.storage_quota_tb_attr.value == "10"
        assert rdf_allocation.storage_quota_tb == 10

    def test_files_quota_attr(self, rdf_allocation, allocation_attribute_factory):
        """Test that files_quota_attr returns the correct attribute."""
        allocation_attribute_factory(
            name="Files Quota", allocation=rdf_allocation, value=1000
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

    def test_storage_quota_tb_bad_value(
        self, rdf_allocation, allocation_attribute_factory
    ):
        """Test that error is thrown when Storage Quota (TB) has a non-integer value."""
        allocation_attribute_factory(
            name="Storage Quota (TB)",
            allocation=rdf_allocation,
            value="not_an_int",
        )
        with pytest.raises(ValueError):
            rdf_allocation.storage_quota_tb

    def test_init_new_allocation(self, project, allocation_active_status):
        """Test a new RDFAllocation can be initialized without a RDF resource."""
        # should not raise an error
        RDFAllocation(
            project=project,
            status=allocation_active_status,
            start_date=timezone.now(),
            end_date=timezone.now(),
        )

    def test_create(self, project, allocation_active_status):
        """Test that RDFAllocation can be created without an RDF resource."""
        RDFAllocation.objects.create(
            project=project,
            status=allocation_active_status,
            start_date=timezone.now(),
            end_date=timezone.now(),
        )

    def test_init_for_saved_non_rdf_allocation(self, project, allocation_active_status):
        """Test initialising RDFAllocation with saved nonRDF Allocation raises error."""
        # create a non-RDF allocation
        allocation = Allocation.objects.create(
            project=project,
            status=allocation_active_status,
            start_date=timezone.now(),
            end_date=timezone.now(),
        )

        with pytest.raises(ValueError):
            RDFAllocation.objects.get(pk=allocation.pk)

        with pytest.raises(ValueError):
            RDFAllocation.from_allocation(allocation)


class TestICLProject:
    """Tests for the ICLProject model."""

    def test_create_iclproject(
        self,
        user,
        settings,
        field_of_science_other,
        project_active_status,
        project_user_active_status,
        project_user_role_manager,
    ):
        """Test that the manager creates the project, membership, and attributes."""
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
            field_of_science=field_of_science_other,
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
        assert project_user.status == project_user_active_status
        assert project_user.role == project_user_role_manager

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

        project.projectattribute_set.get(
            proj_attr_type__name="ASK Ticket Reference",
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

    def test_ask_ticket_reference_attr(self, project, project_attribute_factory):
        """Test that ask_ticket_reference_attr returns the correct attribute."""
        project_attribute_factory(
            name="ASK Ticket Reference", project=project, value="Ref123"
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


@pytest.fixture
def ldap_create_group_mock(mocker):
    """Mock ldap_create_group."""
    return mocker.patch("imperial_coldfront_plugin.models.ldap_create_group")


@pytest.fixture
def get_new_gid_mock(mocker):
    """Mock get_new_gid."""
    return mocker.patch(
        "imperial_coldfront_plugin.models.get_new_gid", return_value=99999
    )


@pytest.fixture
def ldap_gid_in_use_mock(mocker):
    """Mock ldap_gid_in_use."""
    return mocker.patch(
        "imperial_coldfront_plugin.signals.ldap_gid_in_use", return_value=False
    )


@pytest.fixture
def ldap_add_member_to_group_mock(mocker):
    """Mock ldap_add_member_to_group."""
    return mocker.patch("imperial_coldfront_plugin.signals.ldap_add_member_to_group")


class TestHX2Allocation:
    """Tests for the HX2Allocation model."""

    def test_create_hx2allocation(
        self,
        project,
        get_new_gid_mock,
        ldap_gid_in_use_mock,
        ldap_create_group_mock,
        ldap_add_member_to_group_mock,
        allocation_active_status,
        allocation_user_active_status,
    ):
        """Test that the manager correctly create the HX2 Allocation."""
        start_date = datetime.date.today()
        end_date = datetime.date.today() + datetime.timedelta(days=365)

        allocation = HX2Allocation.objects.create_hx2allocation(
            project=project,
            status=allocation_active_status,
            quantity=1,
            start_date=start_date,
            end_date=end_date,
            justification="Test justification",
            description="Test description",
            is_locked=False,
            is_changeable=True,
        )

        # Check that the HX2 Allocation was created with the correct inputs:
        assert isinstance(allocation, HX2Allocation)
        assert allocation.project == project
        assert allocation.status == allocation_active_status
        assert allocation.get_parent_resource.name == "HX2"
        assert allocation.start_date == start_date
        assert allocation.end_date == end_date
        assert allocation.justification == "Test justification"
        assert allocation.description == "Test description"
        assert allocation.is_locked is False
        assert allocation.is_changeable is True

        # Check that the GID attribute was created with the correct value:
        allocation.allocationattribute_set.get(
            allocation_attribute_type__name="GID",
            value=get_new_gid_mock.return_value,
        )

        # Check that the LDAP group creation was called with the correct inputs:
        ldap_create_group_mock.assert_called_once_with(
            group_name=allocation.ldap_shortname,
            gid=get_new_gid_mock.return_value,
        )

        # Check that the AllocationUser was created with the correct inputs:
        allocation.allocationuser_set.get(
            user=project.pi,
            status=allocation_user_active_status,
        )

    def test_create_hx2allocation_ldap_rollback(
        self,
        project,
        get_new_gid_mock,
        ldap_gid_in_use_mock,
        ldap_create_group_mock,
        allocation_active_status,
    ):
        """Test that create_hx2allocation rolls back on LDAP error."""
        ldap_create_group_mock.side_effect = RuntimeError("oh no!")

        with pytest.raises(RuntimeError):
            HX2Allocation.objects.create_hx2allocation(
                project=project,
                status=allocation_active_status,
                quantity=1,
                start_date=datetime.date.today(),
                end_date=datetime.date.today() + datetime.timedelta(days=365),
                justification="Test justification",
                description="Test description",
                is_locked=False,
                is_changeable=True,
            )

        # Ensure that the runtime error came from the LDAP group creation:
        ldap_create_group_mock.assert_called_once()

        # Ensure that no allocation was created in the database:
        assert not Allocation.objects.all()

    def test_create(self, project, allocation_active_status):
        """Test that HX2Allocation can be created without a HX2 resource."""
        HX2Allocation.objects.create(
            project=project,
            status=allocation_active_status,
            start_date=timezone.now(),
            end_date=timezone.now(),
        )

    def test_init_for_saved_non_hx2_allocation(self, project, allocation_active_status):
        """Test initialising HX2Allocation with non-HX2 Allocation raises error."""
        # create a non-RDF allocation
        allocation = Allocation.objects.create(
            project=project,
            status=allocation_active_status,
            start_date=timezone.now(),
            end_date=timezone.now(),
        )

        with pytest.raises(ValueError):
            HX2Allocation.objects.get(pk=allocation.pk)

        with pytest.raises(ValueError):
            HX2Allocation.from_allocation(allocation)

    def test_shortname(self, hx2_allocation, user):
        """Test that shortname returns the correct value."""
        assert hx2_allocation.shortname == user.username

    def test_shortname_missing(self, project, hx2_allocation):
        """Test that ValueError is raised when Shortname attribute is missing."""
        ProjectAttribute.objects.filter(
            project=project,
            proj_attr_type__name="Group ID",
        ).delete()

        with pytest.raises(ValueError, match="Group ID attribute not found"):
            hx2_allocation.shortname

    def test_shortname_multiple(
        self, project, hx2_allocation, project_attribute_factory
    ):
        """Test that ValueError is raised when multiple Shortname attributes exist."""
        project_attribute_factory(
            name="Group ID",
            project=project,
            value="duplicate-short",
        )

        with pytest.raises(ValueError, match="Multiple Group ID attributes"):
            hx2_allocation.shortname

    def test_ldap_shortname(self, hx2_allocation, settings, user):
        """Test that ldap_shortname returns shortname with LDAP prefix."""
        settings.LDAP_HX2_SHORTNAME_PREFIX = "ldap-"
        assert hx2_allocation.ldap_shortname == f"ldap-{user.username}"

    def test_ldap_shortname_empty_prefix(self, hx2_allocation, user, settings):
        """Test that ldap_shortname works with an empty prefix."""
        settings.LDAP_HX2_SHORTNAME_PREFIX = ""
        assert hx2_allocation.ldap_shortname == user.username
