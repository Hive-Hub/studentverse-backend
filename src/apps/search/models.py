from __future__ import annotations

from django.conf import settings
from django.db import models


class SearchQuery(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="search_history"
    )
    query = models.CharField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        username = self.user.username if self.user else "Anonymous"
        return f"{username}: {self.query}"


class RecentlyVisited(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recently_visited"
    )
    entity_type = models.CharField(max_length=50, db_index=True)  # 'community', 'news', 'event'
    entity_id = models.PositiveIntegerField()
    title = models.CharField(max_length=255, blank=True, default="")
    visited_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-visited_at",)
        unique_together = ("user", "entity_type", "entity_id")

    def __str__(self) -> str:
        return f"{self.user.username} visited {self.entity_type} {self.entity_id}: {self.title}"
