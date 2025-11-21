import pytest


@pytest.fixture
def project():
    """Create a test project."""
    from coldfront.core.project.models import Project  # type: ignore

    proj = Project()
    proj.name = "TestProject"
    return proj


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
        assert str(transaction) == "CreditTransaction(id=123, project=TestProject)"

    def test_timestamp_auto_now_add(self):
        """Test that timestamp is automatically set on creation."""
        from imperial_coldfront_plugin import models

        field = models.CreditTransaction._meta.get_field("timestamp")
        assert field.auto_now_add is True

    def test_amount_field(self):
        """Test the amount field configuration."""
        from django.db import models as dj_models  # type: ignore

        from imperial_coldfront_plugin import models

        field = models.CreditTransaction._meta.get_field("amount")
        assert isinstance(field, dj_models.IntegerField)

    def test_description_field(self):
        """Test the description field configuration."""
        from django.db import models as dj_models  # type: ignore

        from imperial_coldfront_plugin import models

        field = models.CreditTransaction._meta.get_field("description")
        assert isinstance(field, dj_models.CharField)
        assert field.max_length == 255

    def test_project_foreign_key(self):
        """Test the project foreign key configuration."""
        from coldfront.core.project.models import Project  # type: ignore

        from imperial_coldfront_plugin import models

        field = models.CreditTransaction._meta.get_field("project")
        assert field.remote_field is not None
        assert field.remote_field.model is Project
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
