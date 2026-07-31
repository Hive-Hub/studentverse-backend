from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from django.utils.deprecation import MiddlewareMixin

from .context import current_request_context


logger = logging.getLogger("apps.logs.request")


class DatabaseLoggingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request._log_started_at = perf_counter()
        request._request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request._request_context_token = current_request_context.set(
            {
                "request_id": request._request_id,
                "request_method": request.method,
                "request_path": request.get_full_path(),
                "remote_addr": self._get_remote_addr(request),
            }
        )

    def process_response(self, request, response):
        self._emit_request_log(request, response.status_code)
        self._reset_context(request)
        response["X-Request-ID"] = getattr(request, "_request_id", uuid4().hex)
        return response

    def process_exception(self, request, exception):
        logger.exception("Unhandled exception while processing request", extra=self._request_extra(request, 500))
        self._reset_context(request)
        return None

    def _emit_request_log(self, request, status_code: int) -> None:
        duration_ms = None
        started_at = getattr(request, "_log_started_at", None)
        if started_at is not None:
            duration_ms = round((perf_counter() - started_at) * 1000, 3)

        extra = self._request_extra(request, status_code)
        extra["duration_ms"] = duration_ms
        logger.info("HTTP %s %s -> %s", request.method, request.path, status_code, extra=extra)

    def _request_extra(self, request, status_code: int) -> dict[str, object]:
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            user_value = user
        else:
            user_value = None
        return {
            "request_context": {
                "request_id": getattr(request, "_request_id", ""),
                "request_method": request.method,
                "request_path": request.get_full_path(),
                "status_code": status_code,
                "remote_addr": self._get_remote_addr(request),
                "user": user_value,
            }
        }

    def _reset_context(self, request) -> None:
        token = getattr(request, "_request_context_token", None)
        if token is not None:
            current_request_context.reset(token)
            request._request_context_token = None

    @staticmethod
    def _get_remote_addr(request):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
