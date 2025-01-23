# Generated by Django 4.2.11 on 2025-01-23 15:47

from django.db import migrations
from django_q.tasks import schedule


def add_prune_groups_task(apps, schema_editor):
    schedule(
        "django.core.management.call_command",
        "prune_groups",
        schedule_type="I",
        minutes=1,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('imperial_coldfront_plugin', '0006_groupmembership_expiration'),
    ]

    operations = [
        migrations.RunPython(add_prune_groups_task),
    ]
