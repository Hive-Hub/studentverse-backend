from __future__ import annotations

from typing import Any
from .models import SearchQuery, RecentlyVisited


def log_search_query(user: Any, query_str: str) -> None:
    """Save user search queries to build search history and trending queries."""
    if not query_str or not query_str.strip():
        return
    query_cleaned = query_str.strip()

    if user and not user.is_anonymous:
        SearchQuery.objects.create(user=user, query=query_cleaned)
    else:
        SearchQuery.objects.create(user=None, query=query_cleaned)


def log_visited_entity(user: Any, entity_type: str, entity_id: int, title: str) -> None:
    """Track user viewed details for news, events, or communities, keeping up to 10 entries."""
    if not user or user.is_anonymous:
        return

    # Delete existing log for this exact entity to move it to the top on re-visits
    RecentlyVisited.objects.filter(user=user, entity_type=entity_type, entity_id=entity_id).delete()

    # Log the visit
    RecentlyVisited.objects.create(
        user=user,
        entity_type=entity_type,
        entity_id=entity_id,
        title=title or ""
    )

    # Prune list length: hold only the 10 most recent entries per user
    visited_qs = RecentlyVisited.objects.filter(user=user).order_by("-visited_at")
    if visited_qs.count() > 10:
        ids_to_keep = visited_qs.values_list("id", flat=True)[:10]
        RecentlyVisited.objects.filter(user=user).exclude(id__in=ids_to_keep).delete()
