from __future__ import annotations

from contextvars import ContextVar
from typing import Any


current_request_context: ContextVar[dict[str, Any] | None] = ContextVar("current_request_context", default=None)
