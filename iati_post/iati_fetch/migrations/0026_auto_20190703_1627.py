# Generated by Django 2.2.3 on 2019-07-03 16:27

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("iati_fetch", "0025_auto_20190703_1602")]

    operations = [
        migrations.AlterField(
            model_name="activity",
            name="element",
            field=django.contrib.postgres.fields.jsonb.JSONField(
                blank=True, db_index=True, null=True
            ),
        )
    ]
