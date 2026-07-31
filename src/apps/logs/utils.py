from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

STANDARD_LOG_RECORD_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


def _coerce_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {key: _coerce_value(inner_value) for key, inner_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_coerce_value(item) for item in value]
    if getattr(value, "is_authenticated", None) is False:
        return None
    if hasattr(value, "pk") and hasattr(value, "__class__") and value.__class__.__name__ != "dict":
        return getattr(value, "pk", str(value))
    return str(value)


def clean_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    return {key: _coerce_value(item) for key, item in value.items()}


def extract_extra(record_dict: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _coerce_value(value)
        for key, value in record_dict.items()
        if key not in STANDARD_LOG_RECORD_KEYS and not key.startswith("_")
    }
