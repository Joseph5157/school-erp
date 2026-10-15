"""Phase 7 bulk import views (ADR 0017). Administrators only."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core import imports
from core.authorization import administrator_required
from core.forms import ImportUploadForm
from core.models import ImportBatch


@administrator_required("core.view_importbatch")
def import_list(request):
    imports.expire_stale_batches()
    batches = ImportBatch.objects.select_related("academic_year", "uploaded_by")[:50]
    return render(request, "core/import_list.html", {"batches": batches})


@administrator_required("core.run_import")
def import_upload(request):
    imports.expire_stale_batches()
    if request.method == "POST":
        form = ImportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            upload = form.cleaned_data["file"]
            try:
                batch = imports.create_batch(
                    user=request.user,
                    file_name=upload.name,
                    data=upload.read(),
                    academic_year=form.cleaned_data["academic_year"],
                    enrollment_start_date=form.cleaned_data["enrollment_start_date"],
                )
            except imports.ImportFileError as problem:
                form.add_error("file", str(problem))
            else:
                return redirect("core:import-detail", pk=batch.pk)
    else:
        form = ImportUploadForm()
    return render(request, "core/import_upload.html", {"form": form})


@administrator_required("core.view_importbatch")
def import_detail(request, pk):
    batch = get_object_or_404(
        ImportBatch.objects.select_related("academic_year", "uploaded_by", "finished_by"), pk=pk
    )
    plan = live_errors = None
    new_warnings = []
    results = batch.row_results.all()
    warnings = [r for r in results if r.level == "WARNING"]
    if batch.is_pending:
        plan, live = imports.preview(batch)
        live_errors = [issue for issue in live if issue.level == "ERROR"]
        recorded = {(r.sheet, r.row_number, r.column, r.message) for r in warnings}
        new_warnings = [
            issue for issue in live
            if issue.level == "WARNING"
            and (issue.sheet, issue.row, issue.column[:50], issue.message[:500]) not in recorded
        ]
    return render(request, "core/import_detail.html", {
        "batch": batch,
        "plan": plan,
        "live_errors": live_errors,
        "new_warnings": new_warnings,
        "needs_review": bool(warnings or new_warnings),
        "errors": [r for r in results if r.level == "ERROR"],
        "warnings": warnings,
        "can_run": request.user.has_perm("core.run_import"),
    })


@administrator_required("core.run_import")
@require_POST
def import_commit(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk)
    try:
        batch = imports.commit_batch(
            batch,
            user=request.user,
            warnings_reviewed=request.POST.get("reviewed_warnings") == "yes",
        )
    except imports.CommitError as problem:
        messages.error(request, str(problem))
    else:
        messages.success(request, f"Imported {batch.summary.get('students', 0)} students.")
    return redirect("core:import-detail", pk=pk)


@administrator_required("core.run_import")
@require_POST
def import_discard(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk)
    if imports.discard_batch(batch, user=request.user):
        messages.info(request, "Import discarded. Nothing was imported.")
    return redirect("core:import-detail", pk=pk)


@administrator_required("core.view_importbatch")
def import_issues_csv(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk)
    response = HttpResponse(imports.issues_csv(batch), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="import-{batch.pk}-problems.csv"'
    return response


@administrator_required("core.run_import")
def import_template(request):
    response = HttpResponse(
        imports.template_workbook(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="school-erp-import-template.xlsx"'
    return response
