"""Guardian Portal URLs (namespace "portal"), separate from the admin ERP."""

from django.urls import path

from core import portal_views

app_name = "portal"

urlpatterns = [
    path("", portal_views.home, name="home"),
    path("children/<uuid:public_id>/", portal_views.child, name="child"),
    path(
        "children/<uuid:public_id>/attendance/", portal_views.attendance, name="attendance"
    ),
    path(
        "children/<uuid:public_id>/report-cards/",
        portal_views.report_cards,
        name="report-cards",
    ),
    path(
        "children/<uuid:public_id>/report-cards/<uuid:publication_id>/",
        portal_views.report_card,
        name="report-card",
    ),
]
