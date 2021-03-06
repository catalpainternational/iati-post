# Generated by Django 2.2.3 on 2019-07-03 15:54

import django.contrib.postgres.fields.jsonb
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("iati_fetch", "0023_auto_20190703_1524")]

    operations = [
        migrations.RemoveField(model_name="activity", name="description"),
        migrations.RemoveField(model_name="activity", name="narrative"),
        migrations.RemoveField(model_name="activity", name="title"),
        migrations.CreateModel(
            name="ActivityNarrative",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "narrative",
                    django.contrib.postgres.fields.jsonb.JSONField(
                        blank=True, null=True
                    ),
                ),
                ("path", models.TextField(blank=True, null=True)),
                (
                    "activity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="iati_fetch.Activity",
                    ),
                ),
            ],
        ),
    ]
