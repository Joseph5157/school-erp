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
]
