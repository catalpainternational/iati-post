# Generated by Django 2.2.3 on 2019-07-02 13:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("iati_fetch", "0016_organisationabbreviation_withdrawn")]

    operations = [
        migrations.AddField(
            model_name="requestcacherecord",
            name="exception",
            field=models.TextField(default=""),
            preserve_default=False,
        )
    ]
