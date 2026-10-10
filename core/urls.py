from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("school/", views.school_detail, name="school-detail"),
    path("school/create/", views.school_create, name="school-create"),
    path("school/edit/", views.school_update, name="school-update"),
    path("academic-years/", views.academic_year_list, name="academic-year-list"),
    path("academic-years/create/", views.academic_year_create, name="academic-year-create"),
    path(
        "academic-years/<int:pk>/calendar/",
        views.academic_year_calendar,
        name="academic-year-calendar",
    ),
    path(
        "academic-years/<int:pk>/calendar/add/",
        views.calendar_day_create,
        name="calendar-day-create",
    ),
    path(
        "academic-years/<int:pk>/calendar/saturdays/",
        views.academic_year_saturday_rule,
        name="academic-year-saturday-rule",
    ),
    path("calendar-days/<int:pk>/edit/", views.calendar_day_update, name="calendar-day-update"),
    path(
        "calendar-days/<int:pk>/delete/",
        views.calendar_day_delete,
        name="calendar-day-delete",
    ),
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
    path("students/", views.student_list, name="student-list"),
    path("students/<int:pk>/", views.student_detail, name="student-detail"),
    path("students/<int:pk>/enroll/", views.student_enroll, name="student-enroll"),
    path(
        "students/<int:pk>/status/",
        views.student_status_change,
        name="student-status-change",
    ),
    path("guardians/", views.guardian_list, name="guardian-list"),
    path("guardians/create/", views.guardian_create, name="guardian-create"),
    path("guardians/<int:pk>/", views.guardian_detail, name="guardian-detail"),
    path("attendance/", views.attendance_register_list, name="attendance-register-list"),
    path(
        "attendance/create/",
        views.attendance_register_create,
        name="attendance-register-create",
    ),
    path(
        "attendance/<int:pk>/",
        views.attendance_register_detail,
        name="attendance-register-detail",
    ),
    path("attendance/<int:pk>/capture/", views.attendance_capture, name="attendance-capture"),
    path(
        "attendance/<int:pk>/submit/",
        views.attendance_register_submit,
        name="attendance-register-submit",
    ),
    path(
        "attendance/entries/<int:pk>/correct/",
        views.attendance_entry_correct,
        name="attendance-entry-correct",
    ),
    path(
        "students/<int:pk>/attendance/",
        views.student_attendance,
        name="student-attendance",
    ),
]
