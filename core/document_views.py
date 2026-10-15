"""Office document pages (spec 2026-10-15). Permission core.issue_document."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from core.authorization import administrator_required
from core.documents import attendance_summary, bonafide, report_card, service
from core.forms import AttendanceSummaryForm, BonafideForm, DocumentStudentForm
from core.models import IssuedDocument, TermPublication
from core.portal import visible_publications


@administrator_required("core.issue_document")
def document_index(request):
    recent = IssuedDocument.objects.select_related("student", "academic_year")[:50]
    return render(request, "core/document_index.html", {"recent": recent})


@administrator_required("core.issue_document")
def bonafide_create(request):
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
    pub = get_object_or_404(TermPublication.objects.select_related("student", "term"), pk=pk)
    document = report_card.document_for(pub, actor=request.user)
    if document is None:
        raise Http404("This report card is not available.")
    return service.pdf_response(document, actor=request.user)


@administrator_required("core.issue_document")
def document_pdf(request, pk):
    document = get_object_or_404(IssuedDocument, pk=pk)
    return service.pdf_response(document, actor=request.user)
