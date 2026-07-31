from __future__ import annotations

from django.db import models
from django.contrib.auth import get_user_model
from apps.communities.models import Community

User = get_user_model()


class Report(models.Model):
    REPORT_TYPES = (
        ("user", "User"),
        ("community", "Community"),
        ("message", "Message"),
        ("news", "News"),
        ("event", "Event"),
    )
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("reviewed", "Reviewed"),
        ("actioned", "Actioned"),
        ("dismissed", "Dismissed"),
    )

    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submitted_reports")
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    target_id = models.CharField(max_length=255)  # Holds ID, slug, or identifier of target
    reason = models.CharField(max_length=255)
    details = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    moderator_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class UserMute(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mutes")
    muted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="given_mutes")
    community = models.ForeignKey(Community, on_delete=models.CASCADE, null=True, blank=True, related_name="mutes")
    reason = models.TextField(blank=True, null=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class CommunityBan(models.Model):
    BAN_TYPES = (
        ("temporary", "Temporary"),
        ("permanent", "Permanent"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="community_bans")
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="bans")
    banned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="given_bans")
    ban_type = models.CharField(max_length=20, choices=BAN_TYPES, default="permanent")
    reason = models.TextField(blank=True, null=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("user", "community")


class BlockedWord(models.Model):
    word = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["word"]

    def save(self, *args, **kwargs):
        self.word = self.word.strip().lower()
        super().save(*args, **kwargs)


class MessageAuditLog(models.Model):
    ACTIONS = (
        ("created", "Created"),
        ("edited", "Edited"),
        ("deleted", "Deleted"),
    )

    message_id = models.IntegerField()
    channel_id = models.IntegerField()
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="audit_messages")
    action = models.CharField(max_length=20, choices=ACTIONS)
    old_content = models.TextField(null=True, blank=True)
    new_content = models.TextField(null=True, blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="performed_audits")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
