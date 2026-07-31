from __future__ import annotations

from django.core.exceptions import ValidationError


ALLOWED_ATTACHMENT_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "video/mp4", "video/quicktime", "video/webm",
    "application/pdf",
    "text/plain",
    "application/zip",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB


def validate_emoji(value: str) -> None:
    """Validate that the emoji field is non-empty and within character limits."""
    if not value or not value.strip():
        raise ValidationError("Emoji cannot be empty.")
    if len(value) > 10:
        raise ValidationError("Emoji must be 10 characters or fewer.")


def validate_attachment_file(file) -> None:
    """Validate attachment file size and MIME type."""
    if hasattr(file, "size") and file.size > MAX_ATTACHMENT_SIZE_BYTES:
        raise ValidationError(
            f"Attachment is too large. Maximum size is 25 MB (got {file.size // (1024*1024)} MB)."
        )
    content_type = getattr(file, "content_type", "")
    if content_type and content_type not in ALLOWED_ATTACHMENT_MIME_TYPES:
        raise ValidationError(
            f"Unsupported file type: {content_type}. Allowed types: images, videos, PDFs, docs, text, zip."
        )
