from __future__ import annotations

from django.conf import settings
from django.db import models
from .storage import SupabaseStorage


class UserProfile(models.Model):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        MODERATOR = "moderator", "Moderator"
        ADMIN = "admin", "Admin"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    firebase_uid = models.CharField(max_length=128, unique=True, null=True, blank=True)
    display_name = models.CharField(max_length=255, blank=True, default="")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT, db_index=True)
    
    # Phase 2 Fields
    profile_photo = models.ImageField(storage=SupabaseStorage(), upload_to="profiles/", null=True, blank=True)
    full_name = models.CharField(max_length=150, blank=True, default="")
    username = models.CharField(max_length=50, unique=True, db_index=True, null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True, default="")
    college = models.CharField(max_length=255, blank=True, default="")
    branch = models.CharField(max_length=255, blank=True, default="")
    year = models.IntegerField(null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)
    interests = models.JSONField(default=list, blank=True)
    github = models.URLField(max_length=255, blank=True, null=True)
    linkedin = models.URLField(max_length=255, blank=True, null=True)
    portfolio = models.URLField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=150, blank=True, default="")
    achievements = models.JSONField(default=list, blank=True)
    is_verified_author = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__username",)

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"


class UserStorageUsage(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="storage_usage")
    bytes_used = models.BigIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.user.username}: {self.bytes_used} bytes used"

