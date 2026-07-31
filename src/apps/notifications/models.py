from __future__ import annotations

from django.conf import settings
from django.db import models


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        COMMUNITY = "community", "Community"
        CHANNEL = "channel", "Channel"
        MENTION = "mention", "Mention"
        REPLY = "reply", "Reply"
        REACTION = "reaction", "Reaction"
        NEWS = "news", "News"
        EVENT = "event", "Event"
        ANNOUNCEMENT = "announcement", "Announcement"
        SYSTEM = "system", "System"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications"
    )
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        db_index=True
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    
    # Store dynamic metadata (e.g. sender, entity_id, entity_type, redirect path)
    data = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.recipient.username} - {self.title} ({self.get_notification_type_display()})"


class PushDevice(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_devices"
    )
    registration_token = models.CharField(max_length=255, unique=True)
    device_type = models.CharField(max_length=50, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user.username} device: {self.registration_token[:15]}..."


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences"
    )
    # Lists of integer IDs stored as JSON arrays
    muted_communities = models.JSONField(default=list, blank=True)
    muted_channels = models.JSONField(default=list, blank=True)
    muted_events = models.JSONField(default=list, blank=True)
    muted_types = models.JSONField(default=list, blank=True)

    def __str__(self) -> str:
        return f"Prefs for {self.user.username}"
