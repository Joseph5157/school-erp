from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("school/", views.school_detail, name="school-detail"),
    path("school/create/", views.school_create, name="school-create"),
    path("school/edit/", views.school_update, name="school-update"),
    path("academic-years/", views.academic_year_list, name="academic-year-list"),
    path("academic-years/create/", views.academic_year_create, name="academic-year-create"),
]
