from __future__ import annotations

from django.core.exceptions import ValidationError

from .models import UserProfile


def validate_firebase_id_token(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Firebase ID token must be a string.")
    token = value.strip()
    if len(token) < 20:
        raise ValidationError("Firebase ID token is invalid.")
    return token


def validate_role(value: str) -> str:
    normalized_role = str(value).strip().lower()
    allowed_roles = {choice_value for choice_value, _ in UserProfile.Role.choices}
    if normalized_role not in allowed_roles:
        raise ValidationError("Role must be Student, Moderator, or Admin.")
    return normalized_role


import re
from urllib.parse import urlparse

def validate_username_chars(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError("Username handle cannot be empty.")
    if not (3 <= len(cleaned) <= 30):
        raise ValidationError("Username handle must be between 3 and 30 characters.")
    if not re.match(r"^[a-zA-Z0-9_]+$", cleaned):
        raise ValidationError("Username handle can only contain letters, numbers, and underscores.")
    return cleaned


def validate_year(value: int | None) -> int | None:
    if value is not None:
        try:
            val_int = int(value)
        except (ValueError, TypeError):
            raise ValidationError("Year must be an integer between 1 and 5.")
        if not (1 <= val_int <= 5):
            raise ValidationError("Year must be an integer between 1 and 5.")
        return val_int
    return value


def validate_list_of_strings(value: any, max_items: int = 20, max_length: int = 50) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError("Field must be a list.")
    if len(value) > max_items:
        raise ValidationError(f"List cannot contain more than {max_items} items.")
    for item in value:
        if not isinstance(item, str):
            raise ValidationError("All items in the list must be strings.")
        if len(item) > max_length:
            raise ValidationError(f"Items in the list cannot exceed {max_length} characters.")
    return value


def validate_social_url(value: str | None, domain: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValidationError(f"Invalid URL: {value}")
    netloc = parsed.netloc.lower()
    if domain not in netloc:
        raise ValidationError(f"URL must belong to domain: {domain}")
    return value

