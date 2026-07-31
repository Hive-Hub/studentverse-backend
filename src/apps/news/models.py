from __future__ import annotations

from django.conf import settings
from django.db import models
from apps.accounts.storage import SupabaseStorage
from apps.communities.models import Community


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True, db_index=True)

    def __str__(self) -> str:
        return self.name


class News(models.Model):
    class NewsType(models.TextChoices):
        ANNOUNCEMENT = "announcement", "Announcement"
        TECHNOLOGY = "technology", "Technology"
        HACKATHON = "hackathon", "Hackathon"
        INTERNSHIP = "internship", "Internship"
        PLACEMENT = "placement", "Placement"
        SCHOLARSHIP = "scholarship", "Scholarship"
        WORKSHOP = "workshop", "Workshop"
        EVENT = "event", "Event"
        RESEARCH = "research", "Research"
        GOVERNMENT = "government", "Government"

    class Scope(models.TextChoices):
        PLATFORM = "platform", "Platform"
        COMMUNITY = "community", "Community"
        COLLEGE = "college", "College"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=255)
    content = models.TextField()
    category = models.CharField(max_length=50, choices=NewsType.choices, db_index=True)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.PLATFORM, db_index=True)
    
    community = models.ForeignKey(Community, on_delete=models.CASCADE, null=True, blank=True, related_name="news_items")
    college = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="news_articles")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    scheduled_publish_at = models.DateTimeField(null=True, blank=True, db_index=True)
    
    is_pinned = models.BooleanField(default=False, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_blocked = models.BooleanField(default=False, db_index=True)
    
    image = models.ImageField(storage=SupabaseStorage(), upload_to="news/images/", null=True, blank=True)
    banner = models.ImageField(storage=SupabaseStorage(), upload_to="news/banners/", null=True, blank=True)
    
    views_count = models.PositiveIntegerField(default=0)
    shares_count = models.PositiveIntegerField(default=0)
    
    tags = models.ManyToManyField(Tag, blank=True, related_name="news_items")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_pinned", "-created_at")

    def __str__(self) -> str:
        return self.title


class NewsLike(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="news_likes")
    news = models.ForeignKey(News, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "news")

    def __str__(self) -> str:
        return f"{self.user.username} liked {self.news.title}"


class NewsBookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="news_bookmarks")
    news = models.ForeignKey(News, on_delete=models.CASCADE, related_name="bookmarks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "news")

    def __str__(self) -> str:
        return f"{self.user.username} bookmarked {self.news.title}"


class NewsReport(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="news_reports")
    news = models.ForeignKey(News, on_delete=models.CASCADE, related_name="reports")
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "news")

    def __str__(self) -> str:
        return f"Report on {self.news.title} by {self.user.username}"


class NewsComment(models.Model):
    news = models.ForeignKey(News, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="news_comments")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"Comment by {self.user.username} on {self.news.title}"


class NewsAttachment(models.Model):
    news = models.ForeignKey(News, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(storage=SupabaseStorage(), upload_to="news/attachments/")
    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()
    mime_type = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.file_name
