# Generated by Django 2.2.2 on 2019-07-02 04:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("iati_fetch", "0009_request_requestcacherecord")]

    operations = [
        migrations.CreateModel(
            name="OrganisationAbbreviation",
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
                ("abbreviation", models.TextField(null=True)),
            ],
        )
    ]
