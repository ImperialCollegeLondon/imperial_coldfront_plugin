from django.db import migrations

def update_consistency_check(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.filter(
        func="imperial_coldfront_plugin.tasks.check_ldap_consistency"
    ).update(func="imperial_coldfront_plugin.tasks.check_rdf_ldap_consistency")


def reverse_update_consistency_check(apps, schema_editor):
    # This ensures basckwards compatibility if the migration is ever rolled back.
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.filter(
        func="imperial_coldfront_plugin.tasks.check_rdf_ldap_consistency"
    ).update(func="imperial_coldfront_plugin.tasks.check_ldap_consistency")


class Migration(migrations.Migration):

    dependencies = [
        ('imperial_coldfront_plugin', '0021_schedule_hx2_ldap_consistency_check'),
    ]

    operations = [
        migrations.RunPython(
            update_consistency_check,
            reverse_code=reverse_update_consistency_check,
        ),
    ]
