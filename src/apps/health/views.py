from __future__ import annotations

import django

from django.conf import settings
from django.db import connections
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.common.responses import error_response, success_response


class HealthCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            return error_response(
                message="Service is unhealthy",
                errors={"database": "Database connection failed"},
                status_code=503,
            )

        return success_response(
            message="Service is healthy",
            data={
                "service": settings.APP_NAME,
                "status": "ok",
                "environment": settings.DJANGO_ENVIRONMENT,
                "version": settings.APP_VERSION,
                "checked_at": timezone.now().isoformat().replace("+00:00", "Z"),
                "database": {"connected": True},
            },
        )


class VersionView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        return success_response(
            message="API version retrieved successfully",
            data={
                "service": settings.APP_NAME,
                "environment": settings.DJANGO_ENVIRONMENT,
                "version": settings.APP_VERSION,
                "django": django.get_version(),
            },
        )
