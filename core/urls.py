from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("school/", views.school_detail, name="school-detail"),
    path("school/create/", views.school_create, name="school-create"),
    path("school/edit/", views.school_update, name="school-update"),
    path("academic-years/", views.academic_year_list, name="academic-year-list"),
    path("academic-years/create/", views.academic_year_create, name="academic-year-create"),
    path("classes/", views.class_grade_list, name="class-grade-list"),
    path("classes/create/", views.class_grade_create, name="class-grade-create"),
    path("classes/<int:pk>/", views.class_grade_detail, name="class-grade-detail"),
    path("classes/<int:pk>/sections/create/", views.section_create, name="section-create"),
]
