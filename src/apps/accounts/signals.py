from __future__ import annotations

import logging
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from apps.accounts.models import UserProfile, UserStorageUsage

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs) -> None:
    """Create UserProfile when a new User is created."""
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={"username": instance.username}
        )


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs) -> None:
    """Ensure UserProfile exists and has username populated."""
    profile, created = UserProfile.objects.get_or_create(user=instance)
    if not created and not profile.username:
        profile.username = instance.username
        profile.save(update_fields=["username"])


@receiver(post_delete)
def auto_delete_file_on_delete(sender, instance, **kwargs) -> None:
    """
    Deletes file from Supabase storage when the model instance is deleted,
    and deducts the file size from the user's storage quota.
    """
    for field in instance._meta.fields:
        if isinstance(field, models.FileField):
            file_field = getattr(instance, field.name)
            if file_field and file_field.name:
                try:
                    # Get size before deleting to update quota
                    file_size = 0
                    try:
                        file_size = file_field.size
                    except Exception:
                        pass

                    # Delete file from storage
                    file_field.storage.delete(file_field.name)
                    logger.info(f"Deleted file {file_field.name} from storage on {sender.__name__} delete.")

                    # Identify user associated with the deleted model
                    author = getattr(instance, "user", None) or getattr(instance, "author", None)
                    if not author and hasattr(instance, "recipient"):
                        author = instance.recipient
                    if sender.__name__ == "UserProfile":
                        author = instance.user

                    # Update UserStorageUsage quota
                    if author and not author.is_anonymous and file_size > 0:
                        usage, _ = UserStorageUsage.objects.get_or_create(user=author)
                        usage.bytes_used = max(0, usage.bytes_used - file_size)
                        usage.save(update_fields=["bytes_used"])
                except Exception as e:
                    logger.warning(f"Could not delete file {file_field.name} on model delete: {e}")
