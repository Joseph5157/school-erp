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
    path("applicants/", views.applicant_list, name="applicant-list"),
    path("applicants/create/", views.applicant_create, name="applicant-create"),
    path("applicants/<int:pk>/", views.applicant_detail, name="applicant-detail"),
    path(
        "applicants/<int:pk>/decision/",
        views.applicant_admission_decision,
        name="applicant-admission-decision",
    ),
    path(
        "applicants/<int:pk>/guardians/add/",
        views.applicant_guardian_create,
        name="applicant-guardian-create",
    ),
    path("applicants/<int:pk>/progress/", views.applicant_progress, name="applicant-progress"),
    path("students/<int:pk>/", views.student_detail, name="student-detail"),
    path("students/<int:pk>/enroll/", views.student_enroll, name="student-enroll"),
    path("guardians/", views.guardian_list, name="guardian-list"),
    path("guardians/create/", views.guardian_create, name="guardian-create"),
    path("guardians/<int:pk>/", views.guardian_detail, name="guardian-detail"),
]
