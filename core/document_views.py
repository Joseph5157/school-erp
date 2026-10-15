"""Office document pages (spec 2026-10-15). Permission core.issue_document."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from core.authorization import administrator_required
from core.documents import bonafide, service
from core.forms import BonafideForm
from core.models import IssuedDocument


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
def document_pdf(request, pk):
    document = get_object_or_404(IssuedDocument, pk=pk)
    return service.pdf_response(document, actor=request.user)
