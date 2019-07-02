from django.contrib import admin  # noqa

from . import models

# Register your models here.

admin.site.register(models.CodelistItem)
admin.site.register(models.Organisation)
admin.site.register(models.Request)
admin.site.register(models.RequestCacheRecord)
admin.site.register(models.Activity)
