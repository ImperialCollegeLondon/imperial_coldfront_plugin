from django.db import migrations


def add_expiry_email_notification_task(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.update_or_create(
        name="Send Expiration Notifications",
        func="imperial_coldfront_plugin.tasks.send_expiration_notifications",
        schedule_type="D",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("imperial_coldfront_plugin", "0008_alter_groupmembership_member"),
    ]

    operations = [
        migrations.RunPython(add_expiry_email_notification_task),
    ]
