from __future__ import annotations

import re
from django.conf import settings
from django.db import models
from apps.communities.models import Channel
from apps.accounts.storage import SupabaseStorage


class Message(models.Model):
    channel = models.ForeignKey(
        Channel,
        on_delete=models.CASCADE,
        related_name="messages",
        db_index=True,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    content = models.TextField(blank=True, default="")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="thread_replies",
        db_index=True,
    )
    gif_url = models.URLField(blank=True, default="")
    mentions = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="message_mentions",
        blank=True,
    )
    is_pinned = models.BooleanField(default=False, db_index=True)
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=["channel", "created_at"]),
            models.Index(fields=["channel", "is_pinned"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self) -> str:
        preview = self.content[:50] if self.content else "[attachment]"
        return f"[{self.channel}] {self.author.username}: {preview}"

    def extract_and_set_mentions(self) -> None:
        """Parse @username patterns from content and set M2M mentions."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        usernames = re.findall(r"@([\w.]+)", self.content or "")
        if usernames:
            users = User.objects.filter(username__in=usernames)
            self.mentions.set(users)
        else:
            self.mentions.clear()


class MessageAttachment(models.Model):
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(
        storage=SupabaseStorage(),
        upload_to="messages/attachments/",
    )
    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100, blank=True, default="")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("uploaded_at",)

    def __str__(self) -> str:
        return f"{self.file_name} (msg:{self.message_id})"


class MessageReaction(models.Model):
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="reactions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_reactions",
    )
    emoji = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user", "emoji")
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.user.username} {self.emoji} -> msg:{self.message_id}"
