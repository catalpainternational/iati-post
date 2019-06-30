# Generated by Django 2.2.2 on 2019-06-30 14:15

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("iati_fetch", "0008_codelistitem_codelist")]

    operations = [
        migrations.CreateModel(
            name="Request",
            fields=[
                ("request_hash", models.TextField(primary_key=True, serialize=False))
            ],
        ),
        migrations.CreateModel(
            name="RequestCacheRecord",
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
                ("when", models.DateTimeField()),
                ("response_code", models.IntegerField()),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="iati_fetch.Request",
                    ),
                ),
            ],
        ),
    ]
