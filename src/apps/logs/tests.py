from __future__ import annotations

import logging

from django.test import TestCase
from django.urls import reverse

from .handlers import DatabaseLogHandler
from .models import LogEntry


class RequestLoggingTests(TestCase):
    def test_health_request_creates_log_entry(self):
        initial_count = LogEntry.objects.count()

        response = self.client.get(reverse("health-check"), HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertGreater(LogEntry.objects.count(), initial_count)

        entry = LogEntry.objects.filter(request_path="/health/").latest("created_at")
        self.assertEqual(entry.level, "INFO")
        self.assertEqual(entry.request_method, "GET")
        self.assertEqual(entry.request_path, "/health/")
        self.assertEqual(entry.status_code, 200)
        self.assertIn("HTTP GET /health/ -> 200", entry.message)


class DatabaseLogHandlerTests(TestCase):
    def test_handler_persists_log_record(self):
        handler = DatabaseLogHandler()
        record = logging.LogRecord(
            name="apps.test",
            level=logging.WARNING,
            pathname=__file__,
            lineno=42,
            msg="Test warning",
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        entry = LogEntry.objects.latest("created_at")
        self.assertEqual(entry.logger_name, "apps.test")
        self.assertEqual(entry.level, "WARNING")
        self.assertEqual(entry.message, "Test warning")
