from __future__ import annotations

import random
import string
from django.conf import settings
from django.db import models
from django.utils.text import slugify
from apps.accounts.storage import SupabaseStorage


def generate_unique_invite_code(length: int = 8) -> str:
    """Generates a unique uppercase alphanumeric invite code."""
    characters = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choices(characters, k=length))
        # We check locally inside the model class to ensure uniqueness
        if not Community.objects.filter(invite_code=code).exists():
            return code


class Community(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, db_index=True)
    description = models.TextField(max_length=1000, blank=True, default="")
    
    # Supabase storage fallbacks
    banner = models.ImageField(storage=SupabaseStorage(), upload_to="communities/banners/", null=True, blank=True)
    icon = models.ImageField(storage=SupabaseStorage(), upload_to="communities/icons/", null=True, blank=True)
    
    invite_code = models.CharField(max_length=12, unique=True, db_index=True)
    is_public = models.BooleanField(default=True, db_index=True)
    rules = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="CommunityMember",
        related_name="communities"
    )

    class Meta:
        verbose_name_plural = "Communities"
        ordering = ("-created_at",)

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Community.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        if not self.invite_code:
            self.invite_code = generate_unique_invite_code()

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class CommunityMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MODERATOR = "moderator", "Moderator"
        MEMBER = "member", "Member"

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("community", "user")
        ordering = ("-joined_at",)

    def __str__(self) -> str:
        return f"{self.user.username} - {self.community.name} ({self.get_role_display()})"


class Channel(models.Model):
    class ChannelType(models.TextChoices):
        ANNOUNCEMENTS = "announcements", "Announcements"
        GENERAL = "general", "General"
        PROJECTS = "projects", "Projects"
        RESOURCES = "resources", "Resources"
        EVENTS = "events", "Events"
        DOUBTS = "doubts", "Doubts"
        RANDOM = "random", "Random"

    class PermissionType(models.TextChoices):
        READ_ONLY = "read_only", "Read Only"
        WRITE = "write", "Write"
        MODERATOR_ONLY = "moderator_only", "Moderator Only"

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="channels")
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    description = models.TextField(max_length=1000, blank=True, default="")
    channel_type = models.CharField(max_length=30, choices=ChannelType.choices, default=ChannelType.GENERAL, db_index=True)
    permission_type = models.CharField(max_length=30, choices=PermissionType.choices, default=PermissionType.WRITE, db_index=True)
    is_pinned = models.BooleanField(default=False, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    order = models.PositiveIntegerField(default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("community", "slug")
        ordering = ("-is_pinned", "order", "created_at")

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base_slug = slugify(self.name.lower())
            slug = base_slug
            counter = 1
            # Check unique slug within the specific community
            while Channel.objects.filter(community=self.community, slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"#{self.name} ({self.community.name})"

