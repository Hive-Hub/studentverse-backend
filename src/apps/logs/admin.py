from __future__ import annotations

from django.contrib import admin

from .models import LogEntry


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "level",
        "logger_name",
        "status_code",
        "request_method",
        "request_path",
        "message",
    )
    list_filter = ("level", "logger_name", "status_code", "request_method", "created_at")
    search_fields = ("message", "logger_name", "request_path", "request_id")
    readonly_fields = tuple(field.name for field in LogEntry._meta.fields)
    ordering = ("-created_at",)
