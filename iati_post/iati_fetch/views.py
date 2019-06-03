from django.apps import apps
from django.shortcuts import redirect
from django.views.generic import TemplateView, View

# Create your views here.


class FrontPage(TemplateView):
    template_name = "iati_fetch/home.html"


class Organisations(TemplateView):
    template_name = "iati_fetch/organisation_list.html"

    def get_context_data(self):
        return {
            "organisations": apps.get_model("iati_fetch", "Organisation").objects.all()
        }


class OrganisationDetail(TemplateView):
    template_name = "iati_fetch/organisation_detail.html"

    def get_context_data(self, organisation_id):
        org = apps.get_model("iati_fetch", "Organisation").objects.get(
            pk=organisation_id
        )
        return {"org": org}


class OrganisationFetchXml(View):
    def get(self, request, organisation_id):
        organisation = apps.get_model("iati_fetch", "Organisation").objects.get(
            pk=organisation_id
        )
        links = organisation.fetchxml()
        return redirect("iati-fetch:org-detail", organisation_id=organisation_id)


class OrganisationFetchJson(View):
    def get(self, request, organisation_id):
        organisation = apps.get_model("iati_fetch", "Organisation").objects.get(
            pk=organisation_id
        )
        links = organisation.fetchjson()
        return redirect("iati-fetch:org-detail", organisation_id=organisation_id)


class OrganisationRefresh(View):
    def get(self, request):
        apps.get_model("iati_fetch", "Organisation").fetch()
        return redirect("iati-fetch:orgs")


class OrganisationDelete(TemplateView):
    def get(self, request):
        apps.get_model("iati_fetch", "Organisation").objects.all().delete()
        return redirect("iati-fetch:orgs")
