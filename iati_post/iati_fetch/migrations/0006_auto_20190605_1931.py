# Generated by Django 2.2.2 on 2019-06-05 19:31

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("iati_fetch", "0005_auto_20190605_1928")]

    operations = [
        migrations.RenameField(
            model_name="activity", old_name="json", new_name="element"
        ),
        migrations.RemoveField(model_name="activity", name="xml"),
    ]
