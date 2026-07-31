from __future__ import annotations

import uuid
from django.conf import settings
from django.db import models
from apps.accounts.storage import SupabaseStorage
from apps.communities.models import Community


class Event(models.Model):
    class Scope(models.TextChoices):
        PLATFORM = "platform", "Platform"
        COMMUNITY = "community", "Community"
        COLLEGE = "college", "College"

    class EventType(models.TextChoices):
        ONLINE = "online", "Online"
        OFFLINE = "offline", "Offline"
        HYBRID = "hybrid", "Hybrid"

    title = models.CharField(max_length=255)
    description = models.TextField()
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.PLATFORM, db_index=True)
    
    community = models.ForeignKey(Community, on_delete=models.CASCADE, null=True, blank=True, related_name="events")
    college = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    
    event_type = models.CharField(max_length=20, choices=EventType.choices, default=EventType.OFFLINE, db_index=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(db_index=True)
    
    banner = models.ImageField(storage=SupabaseStorage(), upload_to="events/banners/", null=True, blank=True)
    seats = models.PositiveIntegerField(null=True, blank=True)
    qr_code_key = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_events")
    is_blocked = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("start_time", "created_at")

    def __str__(self) -> str:
        return self.title


class EventSpeaker(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="speakers")
    name = models.CharField(max_length=150)
    bio = models.TextField(blank=True, default="")
    photo = models.ImageField(storage=SupabaseStorage(), upload_to="events/speakers/", null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.event.title})"


class EventSponsor(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="sponsors")
    name = models.CharField(max_length=150)
    logo = models.ImageField(storage=SupabaseStorage(), upload_to="events/sponsors/", null=True, blank=True)
    website = models.URLField(max_length=255, blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.event.title})"


class EventGalleryImage(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="gallery")
    image = models.ImageField(storage=SupabaseStorage(), upload_to="events/gallery/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Gallery image {self.id} for {self.event.title}"


class EventRSVP(models.Model):
    class Status(models.TextChoices):
        JOINED = "joined", "Joined"
        WAITING_LIST = "waiting_list", "Waiting List"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="rsvps")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_rsvps")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.JOINED, db_index=True)
    attended = models.BooleanField(default=False, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "user")
        ordering = ("joined_at",)

    def __str__(self) -> str:
        return f"{self.user.username} - {self.event.title} ({self.get_status_display()})"


class EventReminder(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="reminders")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_reminders")
    reminder_time = models.DateTimeField(db_index=True)
    sent = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Reminder for {self.user.username} - {self.event.title}"


class EventComment(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_comments")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"Comment by {self.user.username} on {self.event.title}"
