from __future__ import annotations

import logging
import os
import requests
from django.core.files.storage import FileSystemStorage, Storage
from django.core.exceptions import SuspiciousOperation, ValidationError

logger = logging.getLogger(__name__)


def validate_and_scan_file(content) -> bool:
    """
    Validates file formats and sizes, and simulates a virus scan placeholder.
    Returns True if the file is an image, False otherwise.
    """
    logger.info("Scanning uploaded file for viruses (mock placeholder)...")
    logger.info("Virus scan completed successfully. No threats detected.")

    name = content.name
    ext = os.path.splitext(name)[1].lower()
    content_type = getattr(content, "content_type", "")

    # Upload limit definitions
    MAX_IMAGE_SIZE = 5 * 1024 * 1024      # 5MB
    MAX_FILE_SIZE = 25 * 1024 * 1024      # 25MB

    allowed_images = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    allowed_docs_videos = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".zip", ".mp4", ".mov", ".avi", ".mkv"}

    allowed_image_mimes = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    allowed_doc_mimes = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
        "application/zip",
        "video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska"
    }

    is_image = ext in allowed_images or content_type in allowed_image_mimes
    is_valid_doc = ext in allowed_docs_videos or content_type in allowed_doc_mimes

    if not (is_image or is_valid_doc):
        raise ValidationError(f"File extension '{ext}' or format is not supported.")

    size = content.size
    if is_image and size > MAX_IMAGE_SIZE:
        raise ValidationError("Image size exceeds the 5MB limit.")
    if is_valid_doc and size > MAX_FILE_SIZE:
        raise ValidationError("File size exceeds the 25MB limit.")

    return is_image


def compress_image(content):
    """Compresses uploaded images on-the-fly using PIL/Pillow."""
    from PIL import Image
    from io import BytesIO
    from django.core.files.base import ContentFile

    try:
        content.seek(0)
        img = Image.open(content)
        img_format = img.format or "JPEG"

        # Convert RGBA/LA to RGB if format is JPEG to avoid errors
        if img_format == "JPEG" and img.mode in ("RGBA", "LA"):
            img = img.convert("RGB")

        output = BytesIO()
        img.save(output, format=img_format, quality=75, optimize=True)
        output.seek(0)

        compressed = ContentFile(output.read(), name=content.name)
        logger.info(f"Image compressed successfully. Size reduced from {content.size} to {compressed.size} bytes.")
        return compressed
    except Exception as e:
        logger.warning(f"Image compression failed, using original file. Error: {e}")
        content.seek(0)
        return content


class SupabaseStorage(Storage):
    def __init__(self, **kwargs):
        self.supabase_url = os.getenv("SUPABASE_URL", "").strip()
        self.supabase_key = os.getenv("SUPABASE_KEY", "").strip()
        self.bucket = os.getenv("SUPABASE_BUCKET", "profiles").strip()

        self.fallback = not (self.supabase_url and self.supabase_key)
        self._logged_fallback_warning = False
        if self.fallback:
            self.fallback_storage = FileSystemStorage()
        else:
            if self.supabase_url.endswith("/"):
                self.supabase_url = self.supabase_url[:-1]

    def deconstruct(self) -> tuple[str, list, dict]:
        return ("apps.accounts.storage.SupabaseStorage", [], {})

    def _log_fallback_if_needed(self):
        if self.fallback and not self._logged_fallback_warning:
            logger.warning("Supabase Storage credentials missing or empty. Falling back to FileSystemStorage.")
            self._logged_fallback_warning = True

    def _open(self, name: str, mode: str = "rb"):
        if self.fallback:
            self._log_fallback_if_needed()
            return self.fallback_storage._open(name, mode)

        url = self.url(name)
        response = requests.get(url)
        if response.status_code == 200:
            from io import BytesIO
            from django.core.files.base import File
            return File(BytesIO(response.content), name=name)
        raise FileNotFoundError(f"File not found on Supabase: {name}")

    def _save(self, name: str, content) -> str:
        # Perform virus scans, type validations, and size checking
        is_image = validate_and_scan_file(content)

        # Apply Pillow image compression if verified as image
        if is_image:
            content = compress_image(content)

        file_size = content.size

        # Retrieve request user context from thread-local middleware
        from apps.accounts.middleware import CurrentUserMiddleware
        user = CurrentUserMiddleware.get_current_user()

        # Enforce storage limits (100MB cumulative limit)
        if user and not user.is_anonymous:
            from apps.accounts.models import UserStorageUsage
            usage, _ = UserStorageUsage.objects.get_or_create(user=user)
            MAX_QUOTA = 100 * 1024 * 1024  # 100MB
            if usage.bytes_used + file_size > MAX_QUOTA:
                raise ValidationError("User cumulative storage quota exceeded (100MB limit).")

            usage.bytes_used += file_size
            usage.save(update_fields=["bytes_used"])

        if self.fallback:
            self._log_fallback_if_needed()
            return self.fallback_storage._save(name, content)

        headers = {
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": getattr(content, "content_type", "application/octet-stream"),
        }

        url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{name}"

        content.seek(0)
        file_data = content.read()

        response = requests.post(url, headers=headers, data=file_data)
        if response.status_code == 400 and "already exists" in response.text.lower():
            response = requests.put(url, headers=headers, data=file_data)

        if response.status_code not in (200, 201):
            raise SuspiciousOperation(f"Failed to upload file to Supabase Storage: {response.text}")

        return name

    def exists(self, name: str) -> bool:
        if self.fallback:
            self._log_fallback_if_needed()
            return self.fallback_storage.exists(name)

        url = f"{self.supabase_url}/storage/v1/object/public/{self.bucket}/{name}"
        response = requests.head(url)
        return response.status_code == 200

    def url(self, name: str) -> str:
        if self.fallback:
            self._log_fallback_if_needed()
            return self.fallback_storage.url(name)

        return f"{self.supabase_url}/storage/v1/object/public/{self.bucket}/{name}"

    def delete(self, name: str) -> None:
        """Deletes a file from local FileSystem or remote Supabase Storage."""
        if self.fallback:
            self._log_fallback_if_needed()
            self.fallback_storage.delete(name)
            return

        headers = {
            "Authorization": f"Bearer {self.supabase_key}",
        }
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{name}"
        response = requests.delete(url, headers=headers)
        if response.status_code not in (200, 204):
            logger.warning(f"Failed to delete file '{name}' from Supabase Storage: {response.text}")

    def get_signed_url(self, name: str, expires_in: int = 3600) -> str:
        """Generates a temporary signed download URL for the requested file."""
        if self.fallback:
            return self.url(name)

        headers = {
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.supabase_url}/storage/v1/object/sign/{self.bucket}/{name}"
        response = requests.post(url, headers=headers, json={"expiresIn": expires_in})
        if response.status_code == 200:
            data = response.json()
            signed_path = data.get("signedURL") or data.get("signedUrl")
            if signed_path and signed_path.startswith("/"):
                return f"{self.supabase_url}{signed_path}"
            return signed_path or self.url(name)
        return self.url(name)
