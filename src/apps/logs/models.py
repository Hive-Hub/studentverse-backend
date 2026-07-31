from __future__ import annotations

from django.conf import settings
from django.db import models


class LogEntry(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    level = models.CharField(max_length=20, db_index=True)
    logger_name = models.CharField(max_length=255, db_index=True)
    message = models.TextField()
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    request_method = models.CharField(max_length=16, blank=True, default="")
    request_path = models.CharField(max_length=2048, blank=True, default="")
    status_code = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    duration_ms = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    remote_addr = models.GenericIPAddressField(null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="log_entries",
    )
    pathname = models.CharField(max_length=512, blank=True, default="")
    module = models.CharField(max_length=255, blank=True, default="")
    function_name = models.CharField(max_length=255, blank=True, default="")
    line_number = models.PositiveIntegerField(null=True, blank=True)
    process_id = models.PositiveIntegerField(null=True, blank=True)
    thread_id = models.PositiveBigIntegerField(null=True, blank=True)
    exception_text = models.TextField(blank=True, default="")
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("created_at", "level")),
            models.Index(fields=("logger_name", "created_at")),
            models.Index(fields=("request_path", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.level} {self.logger_name}: {self.message[:80]}"
