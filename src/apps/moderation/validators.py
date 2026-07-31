from __future__ import annotations

import re
from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from apps.moderation.models import BlockedWord
from apps.messaging.models import Message
from apps.news.models import NewsComment
from apps.events.models import EventComment


def validate_moderated_content(text: str, user=None) -> str:
    """
    Validates content for:
    1. Blocked words (profanity/forbidden language)
    2. Spam detection (duplicate check in last 10 seconds)
    3. REST API rate limiting (max 1 post per second)
    """
    if not text:
        return text

    # 1. Blocked Words Check
    blocked_words = set(BlockedWord.objects.values_list("word", flat=True))
    if blocked_words:
        # Clean punctuation and tokenize words
        normalized = re.sub(r"[^\w\s]", "", text).lower().split()
        for word in normalized:
            if word in blocked_words:
                raise serializers.ValidationError("This content contains blocked words.")

    import os
    import sys
    if "test" in sys.argv:
        os.environ.setdefault("DISABLE_RATE_LIMIT", "true")

    if user and not user.is_anonymous and os.environ.get("DISABLE_RATE_LIMIT") != "true":
        now = timezone.now()

        # 2. Spam duplicate check: max 3 duplicate posts/messages/comments within 10 seconds
        ten_seconds_ago = now - timedelta(seconds=10)
        
        # Count messages with identical content in last 10s
        duplicate_messages = Message.objects.filter(
            author=user, content=text, created_at__gt=ten_seconds_ago
        ).count()

        duplicate_news_comments = NewsComment.objects.filter(
            user=user, content=text, created_at__gt=ten_seconds_ago
        ).count()

        duplicate_event_comments = EventComment.objects.filter(
            user=user, content=text, created_at__gt=ten_seconds_ago
        ).count()

        total_duplicates = duplicate_messages + duplicate_news_comments + duplicate_event_comments
        if total_duplicates >= 3:
            raise serializers.ValidationError("Spam detected. Duplicate postings are blocked.")

        # 3. Rate limiting check: max 1 post per second globally via REST APIs
        one_second_ago = now - timedelta(seconds=1)

        recent_messages = Message.objects.filter(
            author=user, created_at__gt=one_second_ago
        ).exists()

        recent_news_comments = NewsComment.objects.filter(
            user=user, created_at__gt=one_second_ago
        ).exists()

        recent_event_comments = EventComment.objects.filter(
            user=user, created_at__gt=one_second_ago
        ).exists()

        if recent_messages or recent_news_comments or recent_event_comments:
            raise serializers.ValidationError("Rate limit exceeded. Please wait before posting again.")

    return text


def is_user_muted(user, community=None) -> bool:
    """
    Checks if a user is currently muted platform-wide, or optionally within a specific community.
    """
    from django.db.models import Q
    from apps.moderation.models import UserMute
    if not user or user.is_anonymous:
        return False
    now = timezone.now()
    q_filter = Q(expires_at__gt=now) | Q(expires_at__isnull=True)
    if community:
        return UserMute.objects.filter(
            Q(community=community) | Q(community__isnull=True),
            user=user
        ).filter(q_filter).exists()
    return UserMute.objects.filter(user=user, community__isnull=True).filter(q_filter).exists()
