# Generated by Django 2.2.3 on 2019-07-03 16:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("iati_fetch", "0024_auto_20190703_1554")]

    operations = [
        migrations.RemoveField(model_name="activitynarrative", name="narrative"),
        migrations.AddField(
            model_name="activitynarrative",
            name="lang",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activitynarrative",
            name="text",
            field=models.TextField(blank=True, null=True),
        ),
    ]
