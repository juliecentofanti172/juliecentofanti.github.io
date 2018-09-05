import html
import json
import os
from datetime import datetime, timedelta
from logging import getLogger

import requests
from captcha.fields import CaptchaField
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import Http404, get_object_or_404, redirect, render
from django.template import loader
from django.urls import reverse
from django.views.generic import FormView, TemplateView, View
from registration.backends.hmac.views import RegistrationView
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from concordia.forms import (CaptchaEmbedForm, ConcordiaContactUsForm,
                             ConcordiaUserEditForm, ConcordiaUserForm)
from concordia.models import (Asset, Campaign, Item, PageInUse, Project, Status, Tag,
                              Transcription, UserAssetTagCollection, UserProfile)
from concordia.views_ws import PageInUseCreate, PageInUsePut
from importer.views import CreateCampaignView

logger = getLogger(__name__)

ASSETS_PER_PAGE = 36
PROJECTS_PER_PAGE = 36
ITEMS_PER_PAGE = 36


def concordia_api(relative_path):
    abs_path = "{}/api/v1/{}".format(settings.CONCORDIA["netloc"], relative_path)
    logger.debug("Calling API path %s", abs_path)
    data = requests.get(abs_path).json()

    logger.debug("Received %s", data)
    return data


def get_anonymous_user(user_id=True):
    """
    Get the user called "anonymous" if it exist. Create the user if it doesn't exist
    This is the default concordia user if someone is working on the site without logging in first.
    :parameter: user_id Boolean defaults to True, if true returns user id, otherwise return user object
    :return: User id or User
    """
    anon_user = User.objects.filter(username="anonymous").first()
    if anon_user is None:
        anon_user = User.objects.create_user(
            username="anonymous",
            email="anonymous@anonymous.com",
            password="concanonymous",
        )
    if user_id:
        return anon_user.id
    else:
        return anon_user


class ConcordiaRegistrationView(RegistrationView):
    form_class = ConcordiaUserForm


class AccountProfileView(LoginRequiredMixin, TemplateView):
    template_name = "profile.html"

    def post(self, *args, **kwargs):
        context = self.get_context_data()
        instance = get_object_or_404(User, pk=self.request.user.id)
        form = ConcordiaUserEditForm(
            self.request.POST, self.request.FILES, instance=instance
        )
        if form.is_valid():
            obj = form.save(commit=True)
            obj.id = self.request.user.id
            if (
                not self.request.POST["password1"]
                and not self.request.POST["password2"]
            ):
                obj.password = self.request.user.password
            obj.save()

            if "myfile" in self.request.FILES:
                myfile = self.request.FILES["myfile"]
                profile, created = UserProfile.objects.update_or_create(
                    user=obj, defaults={"myfile": myfile}
                )
        else:
            return HttpResponseRedirect("/account/profile/")
        return redirect(reverse("user-profile"))

    def get_context_data(self, **kws):
        last_name = self.request.user.last_name
        if last_name:
            last_name = " " + last_name
        else:
            last_name = ""

        data = {
            "username": self.request.user.username,
            "email": self.request.user.email,
            "first_name": self.request.user.first_name + last_name,
        }
        profile = UserProfile.objects.filter(user=self.request.user)
        if profile:
            data["myfile"] = profile[0].myfile

        transcriptions = Transcription.objects.filter(
            user_id=self.request.user.id
        ).order_by("-updated_on")

        for t in transcriptions:
            campaign = Campaign.objects.get(id=t.asset.campaign.id)
            t.campaign_name = campaign.slug

        return super().get_context_data(
            **dict(
                kws,
                transcriptions=transcriptions,
                form=ConcordiaUserEditForm(initial=data),
            )
        )


class ConcordiaView(TemplateView):
    template_name = "transcriptions/campaigns.html"

    def get_context_data(self, **kws):
        response = concordia_api("campaigns/")
        return dict(super().get_context_data(**kws), response=response)


class ConcordiaProjectView(TemplateView):
    template_name = "transcriptions/project.html"

    def get_context_data(self, **kws):
        try:
            campaign = Campaign.objects.get(slug=self.args[0])
            project = Project.objects.get(slug=self.args[1])
        except Campaign.DoesNotExist:
            raise Http404
        except Project.DoesNotExist:
            raise Http404

        item_list = Item.objects.filter(campaign=campaign, project=project).order_by(
            "item_id"
        )

        paginator = Paginator(item_list, ITEMS_PER_PAGE)

        if not self.request.GET.get("page"):
            page = 1
        else:
            page = self.request.GET.get("page")

        items = paginator.get_page(page)

        return dict(
            super().get_context_data(**kws),
            campaign=campaign,
            project=project,
            items=items,
        )


class ConcordiaItemView(TemplateView):
    template_name = "transcriptions/item.html"

    def get_context_data(self, **kws):
        try:
            campaign = Campaign.objects.get(slug=self.args[0])
            project = Project.objects.get(slug=self.args[1])
            item = Item.objects.get(slug=self.args[2])
        except Campaign.DoesNotExist:
            raise Http404
        except Project.DoesNotExist:
            raise Http404
        except Item.DoesNotExist:
            raise Http404

        asset_list = Asset.objects.filter(
            campaign=campaign,
            project=project,
            item=item,
            status__in=[Status.EDIT, Status.SUBMITTED, Status.COMPLETED, Status.ACTIVE],
        ).order_by("title", "sequence")
        paginator = Paginator(asset_list, ASSETS_PER_PAGE)

        if not self.request.GET.get("page"):
            page = 1
        else:
            page = self.request.GET.get("page")

        assets = paginator.get_page(page)

        return dict(
            super().get_context_data(**kws),
            campaign=campaign,
            project=project,
            item=item,
            assets=assets,
        )


class ConcordiaCampaignView(TemplateView):
    template_name = "transcriptions/campaign.html"

    def get_context_data(self, **kws):
        try:
            campaign = Campaign.objects.get(slug=self.args[0])
        except Campaign.DoesNotExist:
            raise Http404
        project_list = campaign.project_set.all().order_by("title")
        paginator = Paginator(project_list, PROJECTS_PER_PAGE)

        if not self.request.GET.get("page"):
            page = 1
        else:
            page = self.request.GET.get("page")

        projects = paginator.get_page(page)

        return dict(
            super().get_context_data(**kws), campaign=campaign, projects=projects
        )


class ConcordiaAssetView(TemplateView):
    """
    Class to handle GET ansd POST requests on route /campaigns/<campaign>/asset/<asset>
    """

    template_name = "transcriptions/asset.html"

    state_dictionary = {
        "Save": Status.EDIT,
        "Submit for Review": Status.SUBMITTED,
        "Mark Completed": Status.COMPLETED,
    }

    def check_page_in_use(self, url, user):
        """
        Check the page in use for the asset, return true if in use within the last 5 minutes, otherwise false
        :param url: url to test if in use
        :param user: user id
        :return: True or False
        """
        time_threshold = datetime.now() - timedelta(minutes=5)
        page_in_use_count = (
            PageInUse.objects.filter(page_url=url, updated_on__gt=time_threshold)
            .exclude(user=user)
            .count()
        )

        if page_in_use_count > 0:
            return True
        else:
            return False

    def get_context_data(self, **kws):
        """
        Handle the GET request
        :param kws:
        :return: dictionary of items used in the template
        """

        max_sequence = Asset.objects.filter(campaign__slug=self.args[0]).aggregate(
            Max("sequence")
        )["sequence__max"]

        asset = Asset.objects.get(campaign__slug=self.args[0], slug=self.args[1])
        try:
            prev_asset = Asset.objects.get(
                campaign__slug=self.args[0],
                sequence=(lambda x, y: x - 1 if x > 0 else y)(
                    asset.sequence, max_sequence
                ),
            )
        except Asset.DoesNotExist:
            prev_asset = asset

        try:
            next_asset = Asset.objects.get(
                campaign__slug=self.args[0],
                sequence=(lambda x, y: x + 1 if x < max_sequence else 0)(
                    asset.sequence, max_sequence
                ),
            )
        except Asset.DoesNotExist:
            next_asset = asset

        in_use_url = "/campaigns/%s/asset/%s/" % (asset.campaign.slug, asset.slug)
        current_user_id = (
            self.request.user.id
            if self.request.user.id is not None
            else get_anonymous_user()
        )
        page_in_use = self.check_page_in_use(in_use_url, current_user_id)
        # TODO: in the future, this is from a settings file value
        discussion_hide = True

        # Get all transcriptions, they are no longer tied to a specific user
        transcription = Transcription.objects.filter(asset=asset).last()

        # Get all tags, they are no longer tied to a specific user
        db_tags = UserAssetTagCollection.objects.filter(asset=asset)

        tags = all_tags = None
        if db_tags:
            for tags_in_db in db_tags:
                if tags is None:
                    tags = tags_in_db.tags.all()
                    all_tags = tags
                else:
                    pass
                    all_tags = (
                        tags | tags_in_db.tags.all()
                    ).distinct()  # merge the querysets

        captcha_form = CaptchaEmbedForm()

        same_page_count_for_this_user = PageInUse.objects.filter(
            page_url=in_use_url, user=current_user_id
        ).count()

        page_dict = {"page_url": in_use_url, "user": current_user_id}

        if page_in_use is False and same_page_count_for_this_user == 0:
            # add this page as being in use by this user
            # call the web service which will use the serializer to insert the value.
            # this takes care of deleting old entries in PageInUse table

            factory = APIRequestFactory()
            request = factory.post("/ws/page_in_use%s/" % (in_use_url,), page_dict)
            request.session = self.request.session

            PageInUseCreate.as_view()(request)
        elif same_page_count_for_this_user == 1:
            # update the PageInUse
            obj, created = PageInUse.objects.update_or_create(
                page_url=in_use_url, user=current_user_id
            )

        return dict(
            super().get_context_data(**kws),
            page_in_use=page_in_use,
            asset=asset,
            prev_asset=prev_asset,
            next_asset=next_asset,
            transcription=transcription,
            tags=all_tags,
            captcha_form=captcha_form,
            discussion_hide=discussion_hide,
        )

    def post(self, *args, **kwargs):
        """
        Handle POST from campaigns page for individual asset
        :param args:
        :param kwargs:
        :return: redirect back to same page
        """
        self.get_context_data()
        asset = Asset.objects.get(campaign__slug=self.args[0], slug=self.args[1])

        if self.request.POST.get("action").lower() == "contact a manager":
            return redirect(reverse("contact") + "?pre_populate=true")

        if self.request.user.is_anonymous:
            captcha_form = CaptchaEmbedForm(self.request.POST)
            if not captcha_form.is_valid():
                logger.info("Invalid captcha response")
                return self.get(self.request, *args, **kwargs)
        if "tx" in self.request.POST:
            tx = self.request.POST.get("tx")
            status = self.state_dictionary[self.request.POST.get("action")]
            # Save all transcriptions, we will need this reports
            Transcription.objects.create(
                asset=asset,
                user_id=self.request.user.id
                if self.request.user.id is not None
                else get_anonymous_user(),
                text=tx,
                status=status,
            )
            asset.status = status
            asset.save()
        if "tags" in self.request.POST and self.request.user.is_authenticated == True:
            tags = self.request.POST.get("tags").split(",")
            utags, status = UserAssetTagCollection.objects.get_or_create(
                asset=asset, user_id=self.request.user.id
            )
            all_tag = utags.tags.all().values_list("name", flat=True)
            all_tag_list = list(all_tag)
            delete_tags = [i for i in all_tag_list if i not in tags]
            utags.tags.filter(name__in=delete_tags).delete()
            for tag in tags:
                tag_ob, t_status = Tag.objects.get_or_create(name=tag, value=tag)
                if tag_ob not in utags.tags.all():
                    utags.tags.add(tag_ob)

        return redirect(self.request.path)


class ConcordiaAlternateAssetView(View):
    """
    Class to handle when user opts to work on an alternate asset because another user is already working
    on the original page
    """

    def post(self, *args, **kwargs):
        """
        handle the POST request from the AJAX call in the template when user opts to work on alternate page
        :param request:
        :param args:
        :param kwargs:
        :return: alternate url the client will use to redirect to
        """

        if self.request.is_ajax():
            json_dict = json.loads(self.request.body)
            campaign_slug = json_dict["campaign"]
            asset_slug = json_dict["asset"]
        else:
            campaign_slug = self.request.POST.get("campaign", None)
            asset_slug = self.request.POST.get("asset", None)

        if campaign_slug and asset_slug:
            campaign = Campaign.objects.filter(slug=campaign_slug)

            # select a random asset in this campaign that has status of EDIT
            asset = (
                Asset.objects.filter(campaign=campaign[0], status=Status.EDIT)
                .exclude(slug=asset_slug)
                .order_by("?")
                .first()
            )

            return HttpResponse("/campaigns/%s/asset/%s/" % (campaign_slug, asset.slug))


class ConcordiaPageInUse(View):
    """
    Class to handle AJAX calls from the transcription page
    """

    def post(self, *args, **kwargs):
        """
        handle the post request from the periodic AJAX call from the transcription page
        The primary purpose is to update the entry in PageInUse
        :param args:
        :param kwargs:
        :return: "ok"
        """

        if self.request.is_ajax():
            json_dict = json.loads(self.request.body)
            user = json_dict["user"]
            page_url = json_dict["page_url"]
        else:
            user = self.request.POST.get("user", None)
            page_url = self.request.POST.get("page_url", None)

        if user == "AnonymousUser":
            user = "anonymous"

        if user and page_url:
            user_obj = User.objects.filter(username=user).first()

            # update the PageInUse
            obj, created = PageInUse.objects.update_or_create(
                page_url=page_url, user=user_obj
            )

            if created:
                # delete any other PageInUse with same url
                pages_in_use = PageInUse.objects.filter(page_url=page_url).exclude(
                    user=user_obj
                )
                for page in pages_in_use:
                    page.delete()

        # delete any pages not updated in the last 15 minutes
        from datetime import datetime, timedelta

        time_threshold = datetime.now() - timedelta(minutes=15)
        old_page_entries = PageInUse.objects.filter(updated_on__lt=time_threshold)
        for old_page in old_page_entries:
            old_page.delete()

        return HttpResponse("ok")


class TranscriptionView(TemplateView):
    template_name = "transcriptions/transcription.html"

    def get_context_data(self, **kws):
        transcription = Transcription.objects.get(id=self.args[0])
        transcription_user = get_user_model().objects.get(id=transcription.id)
        return super().get_context_data(
            **dict(
                kws, transcription=transcription, transcription_user=transcription_user
            )
        )


class ToDoView(TemplateView):
    template_name = "todo.html"


class ContactUsView(FormView):
    template_name = "contact.html"
    form_class = ConcordiaContactUsForm
    success_url = "."

    def get_initial(self):
        if self.request.GET.get("pre_populate", None) is None:
            return None
        else:
            return {
                "email": (
                    None if self.request.user.is_anonymous else self.request.user.email
                ),
                "link": (
                    self.request.META.get("HTTP_REFERER")
                    if self.request.META.get("HTTP_REFERER")
                    else None
                ),
            }

    def post(self, *args, **kwargs):
        email = html.escape(self.request.POST.get("email") or "")
        subject = html.escape(self.request.POST.get("subject") or "")
        category = html.escape(self.request.POST.get("category") or "")
        link = html.escape(self.request.POST.get("link") or "")
        story = html.escape(self.request.POST.get("story") or "")

        t = loader.get_template("emails/contact_us_email.txt")
        send_mail(
            subject,
            t.render(
                {
                    "from_email": email,
                    "subject": subject,
                    "category": category,
                    "link": link,
                    "story": story,
                }
            ),
            getattr(settings, "DEFAULT_FROM_EMAIL"),
            [getattr(settings, "DEFAULT_TO_EMAIL")],
            fail_silently=True,
        )

        messages.success(self.request, "Your contact message has been sent...")

        return redirect("contact")


class ExperimentsView(TemplateView):
    def get_template_names(self):
        return ["experiments/{}.html".format(self.args[0])]


class CampaignView(TemplateView):
    template_name = "transcriptions/create.html"

    def post(self, *args, **kwargs):
        self.get_context_data()
        name = self.request.POST.get("name")
        url = self.request.POST.get("url")
        slug = name.replace(" ", "-")

        view = CreateCampaignView.as_view()
        importer_resp = view(self.request, *args, **kwargs)

        return render(self.request, self.template_name, importer_resp.data)


class DeleteCampaignView(TemplateView):
    """
    deletes the campaign
    """

    def get(self, request, *args, **kwargs):
        print("Deleting:", self.args[0])
        campaign = Campaign.objects.get(slug=self.args[0])
        campaign.asset_set.all().delete()
        campaign.delete()
        os.system(
            "rm -rf {0}".format(settings.MEDIA_ROOT + "/concordia/" + campaign.slug)
        )
        return redirect("/campaigns/")


class DeleteAssetView(TemplateView):
    """
    Hides an asset with status inactive. Hided assets does not display in
    asset viiew. After hiding an asset, page redirects to campaign view.
    """

    def get(self, request, *args, **kwargs):

        campaign = Campaign.objects.get(slug=self.args[0])
        asset = Asset.objects.get(slug=self.args[1], campaign=campaign)
        asset.status = Status.INACTIVE
        asset.save()
        return redirect("/campaigns/" + self.args[0] + "/")


class ReportCampaignView(TemplateView):
    """
    Report the campaign
    """

    template_name = "transcriptions/report.html"

    def get(self, request, *args, **kwargs):
        campaign = Campaign.objects.get(slug=self.args[0])
        campaign.asset_set.all()
        projects = (
            campaign.asset_set.values("title")
            .annotate(
                total=Count("title"),
                in_progress=Count("status", filter=Q(status__in=["25", "75", "50"])),
                complete=Count("status", filter=Q(status="100")),
                tags=Count("userassettagcollection__tags", distinct=True),
                contributors=Count("transcription__user_id", distinct=True),
                not_started=Count("status", filter=Q(status="0")),
            )
            .order_by("title")
        )
        paginator = Paginator(projects, ASSETS_PER_PAGE)

        if not self.request.GET.get("page"):
            page = 1
        else:
            page = self.request.GET.get("page")

        projects = paginator.get_page(page)
        return render(self.request, self.template_name, locals())


class FilterCampaigns(generics.ListAPIView):
    def get_queryset(self):
        name_query = self.request.query_params.get("name")
        if name_query:
            queryset = Campaign.objects.filter(slug__contains=name_query).values_list(
                "slug", flat=True
            )
        else:
            queryset = Campaign.objects.all().values_list("slug", flat=True)
        return queryset

    def list(self, request):
        queryset = self.get_queryset()
        from django.http import JsonResponse

        return JsonResponse(list(queryset), safe=False)


def publish_campaign(request, campaign, is_publish):
    """ Publish/Unpublish a campaign to otherr users. On un/publishing campaign,
    it will get does the same effect for all its projects. """

    try:
        campaign = Campaign.objects.get(slug=campaign)
    except Campaign.DoesNotExist:
        raise Http404

    if is_publish == "true":
        campaign.is_publish = True
    else:
        campaign.is_publish = False

    sub_collections = campaign.project_set.all()

    for sc in sub_collections:
        sc.is_publish = True if is_publish == "true" else False
        sc.save()

    campaign.save()

    return JsonResponse(
        {
            "message": "Campaign has been %s."
            % ("published" if is_publish == "true" else "unpublished"),
            "state": True if is_publish == "true" else False,
        },
        safe=True,
    )


def publish_project(request, campaign, project, is_publish):
    """ Publish/Unpublish a project to other users. """

    try:
        sub_collection = Project.objects.get(collection__slug=campaign, slug=project)
    except Project.DoesNotExist:
        raise Http404

    if is_publish == "true":
        sub_collection.is_publish = True
    else:
        sub_collection.is_publish = False

    sub_collection.save()

    return JsonResponse(
        {
            "message": "Project has been %s."
            % ("published" if is_publish == "true" else "unpublished"),
            "state": True if is_publish == "true" else False,
        },
        safe=True,
    )
