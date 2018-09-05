
from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, re_path
from django.views.generic import TemplateView
from django.views.static import serve
from machina.app import board

from exporter import views as exporter_views
from faq.views import FAQView
from importer.views import (CreateCampaignView, check_and_save_campaign_assets,
                            get_task_status)

from . import trans_urls, views, views_ws

for key, value in getattr(settings, "ADMIN_SITE", {}).items():
    setattr(admin.site, key, value)


tx_urlpatterns = (
    [
        re_path(r"^$", views.ConcordiaView.as_view(), name="campaigns"),
        re_path(r"^create/$", views.CampaignView.as_view(), name="create"),
        re_path(
            r"^pageinuse/$", views.ConcordiaPageInUse.as_view(), name="page in use"
        ),
        re_path(
            r"^alternateasset/$",
            views.ConcordiaAlternateAssetView.as_view(),
            name="alternate asset",
        ),
        re_path(r"^([^/]+)/$", views.ConcordiaCampaignView.as_view(), name="campaign"),
        re_path(
            r"exportCSV/([^/]+)/$",
            exporter_views.ExportCampaignToCSV.as_view(),
            name="exportCSV campaign",
        ),
        re_path(
            r"exportBagit/([^/]+)/$",
            exporter_views.ExportCampaignToBagit.as_view(),
            name="exportBagit campaign",
        ),
        re_path(
            r"delete/([^/]+)/$",
            views.DeleteCampaignView.as_view(),
            name="delete campaign",
        ),
        re_path(
            r"^([^/]+)/delete/asset/([^/]+)/$",
            views.DeleteAssetView.as_view(),
            name="delete_asset",
        ),
        re_path(
            r"report/([^/]+)/$",
            views.ReportCampaignView.as_view(),
            name="report campaign",
        ),
        re_path(
            r"^([^/]+)/asset/([^/]+)/$",
            views.ConcordiaAssetView.as_view(),
            name="asset",
        ),
        re_path(
            r"transcription/(\d+)/$",
            views.TranscriptionView.as_view(),
            name="transcription",
        ),
        re_path(
            r"^([^/]+)/([^/]+)/$", views.ConcordiaProjectView.as_view(), name="project"
        ),
        re_path(
            r"^([^/]+)/([^/]+)/([^/]+)/$",
            views.ConcordiaItemView.as_view(),
            name="item",
        ),
        re_path(
            r"publish/campaign/(?P<campaign>[a-zA-Z0-9-]+)/(?P<is_publish>[a-zA-Z]+)/$",
            views.publish_campaign,
            name="publish campaign",
        ),
        re_path(
            r"publish/project/(?P<campaign>[a-zA-Z0-9-]+)/(?P<project>[a-zA-Z0-9-]+)/(?P<is_publish>[a-zA-Z]+)/$",
            views.publish_project,
            name="publish project",
        ),
    ],
    "transcriptions",
)


urlpatterns = [
    re_path(r"^$", TemplateView.as_view(template_name="home.html")),
    re_path(
        r"^about/$", TemplateView.as_view(template_name="about.html"), name="about"
    ),
    re_path(r"^contact/$", views.ContactUsView.as_view(), name="contact"),
    re_path(r"^campaigns/", include(tx_urlpatterns, namespace="transcriptions")),
    re_path(r"^api/v1/", include(trans_urls)),
    re_path(
        r"^account/register/$",
        views.ConcordiaRegistrationView.as_view(),
        name="registration_register",
    ),
    re_path(
        r"^account/profile/$", views.AccountProfileView.as_view(), name="user-profile"
    ),
    re_path(r"^account/", include(settings.REGISTRATION_URLS)),
    re_path(
        r"^experiments/(.+)/$", views.ExperimentsView.as_view(), name="experiments"
    ),
    re_path(r"^wireframes/", include("concordia.experiments.wireframes.urls")),
    re_path(
        r"^privacy-policy/$",
        TemplateView.as_view(template_name="policy.html"),
        name="privacy-policy",
    ),
    re_path(
        r"^cookie-policy/$",
        TemplateView.as_view(template_name="policy.html"),
        name="cookie-policy",
    ),
    re_path(r"^faq/$", FAQView.as_view(), name="faq"),
    re_path(
        r"^legal/$", TemplateView.as_view(template_name="legal.html"), name="legal"
    ),
    re_path(r"^admin/", admin.site.urls),
    # Apps
    re_path(r"^forum/", include(board.urls)),
    # Web Services
    re_path(r"^ws/page_in_use/(?P<page_url>(.*?))/$", views_ws.PageInUseGet.as_view()),
    re_path(
        r"^ws/page_in_use_update/(?P<page_url>(.*?))/$", views_ws.PageInUsePut.as_view()
    ),
    re_path(r"^ws/page_in_use/$", views_ws.PageInUseCreate.as_view()),
    re_path(
        r"^ws/page_in_use_user/(?P<user>(.*?))/(?P<page_url>(.*?))/$",
        views_ws.PageInUseUserGet.as_view(),
    ),
    re_path(r"^ws/campaign/(?P<slug>(.*?))/$", views_ws.CampaignGet().as_view()),
    re_path(r"^ws/asset/(?P<campaign>(.*?))/$", views_ws.AssetsList().as_view()),
    re_path(
        r"^ws/asset_by_slug/(?P<campaign>(.*?))/(?P<slug>(.*?))/$",
        views_ws.AssetBySlug().as_view(),
    ),
    re_path(
        r"^ws/page_in_use_filter/(?P<user>(.*?))/(?P<page_url>(.*?))/$",
        views_ws.PageInUseFilteredGet.as_view(),
    ),
    re_path(
        r"^ws/transcription/(?P<asset>(.*?))/$",
        views_ws.TranscriptionLastGet().as_view(),
    ),
    re_path(r"^ws/transcription_create/$", views_ws.TranscriptionCreate().as_view()),
    re_path(r"^ws/tags/(?P<asset>(.*?))/$", views_ws.UserAssetTagsGet().as_view()),
    re_path(r"^ws/tag_create/$", views_ws.TagCreate.as_view()),
]

urlpatterns += [
    re_path(r"^password_reset/$", auth_views.password_reset, name="password_reset"),
    re_path(
        r"^password_reset/done/$",
        auth_views.password_reset_done,
        name="password_reset_done",
    ),
    re_path(
        r"^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$",
        auth_views.password_reset_confirm,
        name="password_reset_confirm",
    ),
    re_path(
        r"^reset/done/$",
        auth_views.password_reset_complete,
        name="password_reset_complete",
    ),
]

urlpatterns += [
    re_path(
        r"^create_campaign/$", CreateCampaignView.as_view(), name="create_campaign"
    ),
    re_path(
        r"^get_task_status/(?P<task_id>[a-zA-Z0-9-]+)$",
        get_task_status,
        name="get_task_status",
    ),
    re_path(
        r"^check_and_save_campaign_assets/(?P<task_id>[a-zA-Z0-9-]+)/(?P<item_id>[a-zA-Z0-9-]+)$",
        check_and_save_campaign_assets,
        name="check_and_save_campaign_item_assets",
    ),
    re_path(
        r"^check_and_save_campaign_assets/(?P<task_id>[a-zA-Z0-9-]+)/$",
        check_and_save_campaign_assets,
        name="check_and_save_campaign_assets",
    ),
    re_path(
        r"^filter/campaigns/$", views.FilterCampaigns.as_view(), name="filter_campaigns"
    ),
]

urlpatterns += [
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT})
]

urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})
]

urlpatterns += [url("", include("django_prometheus_metrics.urls"))]

urlpatterns += [url(r"^captcha/", include("captcha.urls"))]
