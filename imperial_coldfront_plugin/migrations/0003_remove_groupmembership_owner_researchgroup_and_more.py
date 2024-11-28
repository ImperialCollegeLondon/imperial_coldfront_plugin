# Generated by Django 4.2.11 on 2024-11-25 15:53

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('imperial_coldfront_plugin', '0002_unixuid'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='groupmembership',
            name='owner',
        ),
        migrations.CreateModel(
            name='ResearchGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gid', models.IntegerField()),
                ('name', models.CharField(max_length=255)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='groupmembership',
            name='group',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='imperial_coldfront_plugin.researchgroup'),
            preserve_default=False,
        ),
    ]