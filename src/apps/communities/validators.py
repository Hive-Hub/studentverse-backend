from __future__ import annotations

import os
import re
from django.core.exceptions import ValidationError


def validate_community_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError("Community name cannot be empty.")
    if not (3 <= len(cleaned) <= 100):
        raise ValidationError("Community name must be between 3 and 100 characters.")
    if not re.match(r"^[a-zA-Z0-9_\-\s]+$", cleaned):
        raise ValidationError(
            "Community name can only contain letters, numbers, spaces, hyphens, and underscores."
        )
    return cleaned


def validate_image_file(value) -> any:
    if value:
        max_size = 5 * 1024 * 1024
        if value.size > max_size:
            raise ValidationError("Image file size cannot exceed 5MB.")
        
        ext = os.path.splitext(value.name)[1].lower()
        valid_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
        if ext not in valid_extensions:
            raise ValidationError(
                f"Unsupported file extension. Allowed extensions: {', '.join(valid_extensions)}"
            )
    return value


def validate_channel_name(value: str) -> str:
    # Normalize to lowercase and strip whitespace
    cleaned = value.strip().lower()
    if not cleaned:
        raise ValidationError("Channel name cannot be empty.")
    if not (2 <= len(cleaned) <= 100):
        raise ValidationError("Channel name must be between 2 and 100 characters.")
    if not re.match(r"^[a-z0-9]([a-z0-9_\-]*)$", cleaned):
        raise ValidationError(
            "Channel name must start with a lowercase letter or number, and can only contain lowercase letters, numbers, hyphens, and underscores."
        )
    return cleaned

