# Generated by Django 2.2.2 on 2019-06-05 19:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("iati_fetch", "0004_auto_20190603_1505")]

    operations = [
        migrations.RenameField(
            model_name="organisation", old_name="iatiorganisation", new_name="element"
        ),
        migrations.AddField(
            model_name="organisation",
            name="abbreviation",
            field=models.TextField(null=True),
        ),
    ]
