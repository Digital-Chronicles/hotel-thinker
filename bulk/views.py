from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.utils.text import slugify

from .forms import BulkImportForm, BulkExportForm
from .models import BulkJob
from .registry import get_model_from_label
from .services import (
    import_csv,
    queryset_to_csv,
    sample_csv_response,
    field_reference,
)


def staff_required(user):
    return user.is_authenticated and user.is_staff


@login_required
@user_passes_test(staff_required)
def dashboard(request):
    jobs = BulkJob.objects.select_related("created_by")[:50]

    stats = BulkJob.objects.aggregate(
        total_jobs=Count("id"),
        total_rows=Sum("total_rows"),
        success_rows=Sum("success_rows"),
        failed_rows=Sum("failed_rows"),
    )

    total_jobs = stats["total_jobs"] or 0
    success_jobs = BulkJob.objects.filter(status=BulkJob.STATUS_SUCCESS).count()
    failed_jobs = BulkJob.objects.filter(status=BulkJob.STATUS_FAILED).count()
    partial_jobs = BulkJob.objects.filter(status=BulkJob.STATUS_PARTIAL).count()

    success_rate = 0
    if total_jobs:
        success_rate = round((success_jobs / total_jobs) * 100, 1)

    return render(request, "bulk/dashboard.html", {
        "jobs": jobs,
        "total_jobs": total_jobs,
        "success_jobs": success_jobs,
        "failed_jobs": failed_jobs,
        "partial_jobs": partial_jobs,
        "success_rate": success_rate,
        "total_rows": stats["total_rows"] or 0,
        "success_rows": stats["success_rows"] or 0,
        "failed_rows": stats["failed_rows"] or 0,
    })


@login_required
@user_passes_test(staff_required)
def import_data(request):
    if request.method == "POST":
        form = BulkImportForm(request.POST, request.FILES)

        if form.is_valid():
            model_label = form.cleaned_data["model_label"]
            model = get_model_from_label(model_label)
            uploaded_file = form.cleaned_data["csv_file"]

            result = import_csv(
                model=model,
                uploaded_file=uploaded_file,
                update_existing=form.cleaned_data["update_existing"],
            )

            status = BulkJob.STATUS_SUCCESS

            if result["failed"] and result["success"]:
                status = BulkJob.STATUS_PARTIAL
            elif result["failed"] and not result["success"]:
                status = BulkJob.STATUS_FAILED

            BulkJob.objects.create(
                action=BulkJob.ACTION_IMPORT,
                app_label=model._meta.app_label,
                model_name=model._meta.model_name,
                file_name=uploaded_file.name,
                total_rows=result["total"],
                success_rows=result["success"],
                failed_rows=result["failed"],
                status=status,
                message="\n".join(result["errors"][:200]),
                created_by=request.user,
            )

            if status == BulkJob.STATUS_SUCCESS:
                messages.success(request, f"Imported {result['success']} rows successfully.")
            else:
                first_error = result["errors"][0] if result["errors"] else "Unknown error."
                messages.warning(
                    request,
                    f"Imported {result['success']} rows, failed {result['failed']} rows. First error: {first_error}"
                )

            return redirect("bulk:dashboard")

    else:
        form = BulkImportForm()

    return render(request, "bulk/import.html", {"form": form})


@login_required
@user_passes_test(staff_required)
def export_data(request):
    if request.method == "POST":
        form = BulkExportForm(request.POST)

        if form.is_valid():
            model = get_model_from_label(form.cleaned_data["model_label"])
            queryset = model.objects.all().order_by(model._meta.pk.name)

            limit = form.cleaned_data.get("limit") if "limit" in form.cleaned_data else 0

            if limit:
                queryset = queryset[:limit]

            csv_data = queryset_to_csv(model, queryset)
            filename = f"{slugify(model._meta.app_label)}-{slugify(model._meta.model_name)}.csv"
            total = queryset.count() if hasattr(queryset, "count") else len(queryset)

            BulkJob.objects.create(
                action=BulkJob.ACTION_EXPORT,
                app_label=model._meta.app_label,
                model_name=model._meta.model_name,
                file_name=filename,
                total_rows=total,
                success_rows=total,
                failed_rows=0,
                status=BulkJob.STATUS_SUCCESS,
                created_by=request.user,
            )

            response = HttpResponse(csv_data, content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

    else:
        form = BulkExportForm()

    return render(request, "bulk/export.html", {"form": form})


@login_required
@user_passes_test(staff_required)
def download_template(request):
    model_label = request.GET.get("model")

    if not model_label:
        messages.error(request, "Choose a model first.")
        return redirect("bulk:import")

    model = get_model_from_label(model_label)
    csv_data = sample_csv_response(model)
    filename = f"template-{slugify(model._meta.app_label)}-{slugify(model._meta.model_name)}.csv"

    response = HttpResponse(csv_data, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@user_passes_test(staff_required)
def model_fields(request):
    model_label = request.GET.get("model")

    if not model_label:
        return JsonResponse({"fields": []})

    try:
        model = get_model_from_label(model_label)
        return JsonResponse({"fields": field_reference(model)})
    except Exception as exc:
        return JsonResponse({"fields": [], "error": str(exc)}, status=400)