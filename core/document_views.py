"""Office document pages (spec 2026-10-15). Permission core.issue_document.

`issue_document` opens the Documents area. What a document contains decides the rest (Security
Gate 4B, core/data_access.py): choosing a student needs view_student, a report card needs
view_studentresult, an attendance summary needs view_attendanceentry, and a direct request for
a document without that permission is a 403.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from core import data_access
from core.authorization import administrator_required
from core.documents import attendance_summary, bonafide, report_card, service
from core.forms import AttendanceSummaryForm, BonafideForm, DocumentStudentForm
from core.models import IssuedDocument, TermPublication
from core.portal import visible_publications


@administrator_required("core.issue_document")
def document_index(request):
    # Only documents this login could open (their student names are student data too).
    recent = IssuedDocument.objects.filter(
        document_type__in=data_access.openable_document_types(request.user)
    ).select_related("student", "academic_year")[:50]
    return render(request, "core/document_index.html", {"recent": recent})


@administrator_required("core.issue_document")
def bonafide_create(request):
    if not request.user.has_perm(data_access.STUDENT):  # choosing a student lists students
        raise PermissionDenied
    form = BonafideForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            document = bonafide.issue_bonafide(
                student=form.cleaned_data["student"],
                purpose_key=form.cleaned_data["purpose"],
                purpose_text=form.cleaned_data["purpose_text"],
                actor=request.user,
            )
        except ValidationError as problem:
            form.add_error(None, problem.messages[0])
        else:
            messages.success(request, f"Certificate {document.serial} issued.")
            return redirect("core:document-pdf", pk=document.pk)
    return render(request, "core/bonafide_form.html", {"form": form})


@administrator_required("core.issue_document")
def attendance_summary_page(request):
    if not request.user.has_perm(data_access.ATTENDANCE_ENTRY):  # per-student counts
        raise PermissionDenied
    posting = request.method == "POST"
    form = AttendanceSummaryForm(request.POST if posting else (request.GET or None))
    summary = None
    if form.is_valid():
        data = form.cleaned_data
        try:
            if posting:
                document = attendance_summary.issue_summary(
                    data["section"], data["start"], data["end"], actor=request.user)
                messages.success(request, f"Summary {document.serial} issued.")
                return redirect("core:document-pdf", pk=document.pk)
            summary = attendance_summary.build(data["section"], data["start"], data["end"])
        except ValidationError as problem:
            form.add_error(None, problem.messages[0])
    return render(request, "core/attendance_summary.html", {"form": form, "summary": summary})


@administrator_required("core.issue_document")
def document_report_cards(request):
    if not (
        request.user.has_perm(data_access.STUDENT)  # choosing a student
        and request.user.has_perm(data_access.STUDENT_RESULT)  # the report cards are marks
    ):
        raise PermissionDenied
    form = DocumentStudentForm(request.GET or None)
    student = publications = None
    if form.is_valid():
        student = form.cleaned_data["student"]
        publications = visible_publications(student)
    return render(request, "core/document_report_cards.html", {
        "form": form, "student": student, "publications": publications,
    })


@administrator_required("core.issue_document")
def document_report_card_pdf(request, pk):
    if not request.user.has_perm(data_access.STUDENT_RESULT):  # a report card is marks
        raise PermissionDenied
    pub = get_object_or_404(TermPublication.objects.select_related("student", "term"), pk=pk)
    document = report_card.document_for(pub, actor=request.user)
    if document is None:
        raise Http404("This report card is not available.")
    return service.pdf_response(document, actor=request.user)


@administrator_required("core.issue_document")
def document_pdf(request, pk):
    document = get_object_or_404(IssuedDocument.objects.select_related("publication"), pk=pk)
    if not data_access.can_open_document(request.user, document):
        raise PermissionDenied  # what the document contains decides who may open it
    if (document.document_type == IssuedDocument.DocumentType.REPORT_CARD
            and not report_card.is_current(document)):
        messages.error(
            request,
            f"Report card {document.serial} is no longer current: its results were "
            "corrected or withdrawn. Print the current report card instead.",
        )
        return redirect("core:document-index")
    return service.pdf_response(document, actor=request.user)
