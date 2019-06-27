# Generated by Django 2.2.2 on 2019-06-27 09:42

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("iati_fetch", "0006_auto_20190605_1931")]

    operations = [
        migrations.CreateModel(
            name="Codelist",
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
                ("element", django.contrib.postgres.fields.jsonb.JSONField(null=True)),
            ],
        ),
        migrations.CreateModel(
            name="CodelistItem",
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
                ("element", django.contrib.postgres.fields.jsonb.JSONField(null=True)),
            ],
        ),
    ]
