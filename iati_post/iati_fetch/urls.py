from django.urls import path
from . import views

app_name = "iati-fetch"

urlpatterns = [
    path("", views.FrontPage.as_view(), name="index"),
    path("orgs", views.Organisations.as_view(), name="orgs"),
    # This will be a websocket one day
    path("org_fetch", views.OrganisationRefresh.as_view(), name="org-fetch"),
    path("org_delete", views.OrganisationDelete.as_view(), name="org-delete"),
    path(
        "org_fetch_xml/<str:organisation_id>",
        views.OrganisationFetchXml.as_view(),
        name="org-fetch-xml",
    ),
    path(
        "org_fetch_json/<str:organisation_id>",
        views.OrganisationFetchJson.as_view(),
        name="org-fetch-json",
    ),
    path(
        "org_detail/<str:organisation_id>",
        views.OrganisationDetail.as_view(),
        name="org-detail",
    ),
]
