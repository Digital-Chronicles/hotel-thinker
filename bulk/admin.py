from django.contrib import admin
from .models import BulkJob


@admin.register(BulkJob)
class BulkJobAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "action",
        "app_label",
        "model_name",
        "status",
        "total_rows",
        "success_rows",
        "failed_rows",
        "created_by",
    )

    list_filter = (
        "action",
        "status",
        "app_label",
        "created_at",
    )

    search_fields = (
        "app_label",
        "model_name",
        "file_name",
        "message",
    )

    readonly_fields = (
        "action",
        "app_label",
        "model_name",
        "file_name",
        "total_rows",
        "success_rows",
        "failed_rows",
        "status",
        "message",
        "created_by",
        "created_at",
    )

    ordering = ("-created_at",)