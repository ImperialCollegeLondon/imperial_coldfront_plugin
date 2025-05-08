from django.db import migrations

from coldfront.core.allocation.models import AllocationAttributeType, AttributeType


def add_gid_attribute_type(apps, schema_editor):
    """Add a private AllocationAttributeType of "GID" via data migration."""
    AllocationAttributeType = apps.get_model("allocation", "AllocationAttributeType")
    AttributeType = apps.get_model("allocation", "AttributeType")

    text_attribute_type, _ = AttributeType.objects.get_or_create(name="Text")
    AllocationAttributeType.objects.get_or_create(
        name="GID",
        defaults=dict(
            attribute_type=text_attribute_type,
            is_unique=True,
            is_private=True,
            is_changeable=False,
        ),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("imperial_coldfront_plugin", "0013_auto_20250508_1115"),
    ]

    operations = [
        migrations.RunPython(add_gid_attribute_type),
    ]
