from __future__ import annotations

from rest_framework import serializers
from apps.news.models import Tag
from .models import SearchQuery, RecentlyVisited


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name")


class SearchQuerySerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchQuery
        fields = ("id", "query", "created_at")


class RecentlyVisitedSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecentlyVisited
        fields = ("id", "entity_type", "entity_id", "title", "visited_at")
