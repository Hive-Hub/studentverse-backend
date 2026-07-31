from __future__ import annotations

import logging
from contextvars import ContextVar

from django.db import close_old_connections

from .context import current_request_context
from .utils import clean_mapping, extract_extra


_logging_guard: ContextVar[bool] = ContextVar("database_log_handler_guard", default=False)


class DatabaseLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if _logging_guard.get():
            return

        token = _logging_guard.set(True)
        try:
            from django.apps import apps
            if not apps.ready:
                return

            close_old_connections()
            from .models import LogEntry

            request_context = current_request_context.get() or {}
            record_context = clean_mapping(getattr(record, "request_context", None))
            merged_context = {**request_context, **record_context}
            extra = extract_extra(record.__dict__)
            exception_text = ""
            if record.exc_info:
                exception_text = logging.Formatter().formatException(record.exc_info)

            def do_save():
                LogEntry.objects.create(
                    level=record.levelname,
                    logger_name=record.name,
                    message=record.getMessage(),
                    request_id=str(merged_context.get("request_id", "") or ""),
                    request_method=str(merged_context.get("request_method", "") or ""),
                    request_path=str(merged_context.get("request_path", "") or ""),
                    status_code=merged_context.get("status_code"),
                    duration_ms=merged_context.get("duration_ms"),
                    remote_addr=merged_context.get("remote_addr"),
                    user_id=getattr(merged_context.get("user"), "pk", merged_context.get("user")),
                    pathname=record.pathname or "",
                    module=record.module or "",
                    function_name=record.funcName or "",
                    line_number=record.lineno or None,
                    process_id=record.process or None,
                    thread_id=record.thread or None,
                    exception_text=exception_text,
                    extra=extra,
                )

            import asyncio
            import threading
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    t = threading.Thread(target=do_save)
                    t.start()
                    t.join()
                    return
            except RuntimeError:
                pass

            do_save()
        except Exception:
            self.handleError(record)
        finally:
            _logging_guard.reset(token)
