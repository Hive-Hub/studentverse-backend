from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def success_response(
    *,
    message: str,
    data: Any = None,
    status_code: int = status.HTTP_200_OK,
    meta: Mapping[str, Any] | None = None,
) -> Response:
    payload: dict[str, Any] = {
        "success": True,
        "message": message,
        "data": data,
    }
    if meta is not None:
        payload["meta"] = dict(meta)
    return Response(payload, status=status_code)


def error_response(
    *,
    message: str,
    errors: Any = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    meta: Mapping[str, Any] | None = None,
) -> Response:
    payload: dict[str, Any] = {
        "success": False,
        "message": message,
    }
    if errors is not None:
        payload["errors"] = errors
    if meta is not None:
        payload["meta"] = dict(meta)
    return Response(payload, status=status_code)


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    message = "An unexpected error occurred"
    errors: Any = response.data

    if isinstance(response.data, dict):
        detail = response.data.get("detail")
        if detail is not None:
            message = str(detail)
            if len(response.data) == 1:
                errors = None
            else:
                errors = {key: value for key, value in response.data.items() if key != "detail"}
        elif response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            message = "An unexpected error occurred"
    elif isinstance(response.data, list):
        errors = response.data

    response.data = {
        "success": False,
        "message": message,
    }
    if errors is not None:
        response.data["errors"] = errors
    return response
