from django.conf import settings
from django.db import models
from django.utils import timezone


class BulkJob(models.Model):
    ACTION_IMPORT = "import"
    ACTION_EXPORT = "export"

    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_PARTIAL = "partial"

    ACTION_CHOICES = (
        (ACTION_IMPORT, "Import"),
        (ACTION_EXPORT, "Export"),
    )

    STATUS_CHOICES = (
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_PARTIAL, "Partial Success"),
    )

    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    app_label = models.CharField(max_length=80)
    model_name = models.CharField(max_length=120)

    file_name = models.CharField(max_length=255, blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    success_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SUCCESS,
    )

    message = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bulk_jobs",
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bulk Job"
        verbose_name_plural = "Bulk Jobs"
        indexes = [
            models.Index(fields=["action", "status"]),
            models.Index(fields=["app_label", "model_name"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.app_label}.{self.model_name} - {self.status}"