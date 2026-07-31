from __future__ import annotations

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, status, permissions, pagination
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from apps.common.responses import success_response, error_response
from apps.communities.models import Community, Channel
from apps.messaging.models import Message
from apps.news.models import News, Tag
from apps.events.models import Event

from apps.news.serializers import NewsSerializer, NewsAuthorSerializer
from apps.events.serializers import EventSerializer
from apps.communities.serializers import CommunitySerializer, ChannelSerializer
from apps.messaging.serializers import MessageSerializer

from .models import SearchQuery, RecentlyVisited
from .serializers import SearchQuerySerializer, RecentlyVisitedSerializer, TagSerializer
from .services import log_search_query, log_visited_entity

User = get_user_model()


class GlobalSearchPagination(pagination.PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class GlobalSearchViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = GlobalSearchPagination

    def get_serializer_class(self):
        # Default serializer for search history
        return SearchQuerySerializer

    @action(detail=False, methods=["get"])
    def query(self, request) -> Response:
        """Perform a global search returning matched users, communities, news, events, and tags."""
        q = request.query_params.get("q", "").strip()
        type_param = request.query_params.get("type", "all").lower()
        sort_param = request.query_params.get("sort", "relevance").lower()
        scope_param = request.query_params.get("scope", "all").lower()

        # Log search query
        if q:
            log_search_query(request.user, q)

        user_profile = getattr(request.user, "profile", None)
        user_role = user_profile.role if user_profile else "student"
        user_communities = request.user.community_memberships.values_list("community_id", flat=True)

        # 1. Users Query
        users_qs = User.objects.filter(
            Q(username__icontains=q) | Q(profile__username__icontains=q) | Q(profile__display_name__icontains=q)
        ).distinct()

        # 2. Communities Query
        communities_qs = Community.objects.all()
        if user_role not in ["admin", "moderator"]:
            communities_qs = communities_qs.filter(
                Q(is_public=True) | Q(memberships__user=request.user)
            ).distinct()
        communities_qs = communities_qs.filter(
            Q(name__icontains=q) | Q(description__icontains=q)
        )

        # 3. Channels Query
        channels_qs = Channel.objects.all()
        if user_role not in ["admin", "moderator"]:
            channels_qs = channels_qs.filter(
                Q(community__is_public=True) | Q(community__memberships__user=request.user)
            ).distinct()
        channels_qs = channels_qs.filter(
            Q(name__icontains=q) | Q(description__icontains=q)
        )

        # 4. Messages Query
        messages_qs = Message.objects.all()
        if user_role not in ["admin", "moderator"]:
            messages_qs = messages_qs.filter(
                Q(channel__community__is_public=True) | Q(channel__community__memberships__user=request.user)
            ).distinct()
        messages_qs = messages_qs.filter(content__icontains=q)

        # 5. News Query
        news_qs = News.objects.filter(is_blocked=False)
        if scope_param == "community":
            news_qs = news_qs.filter(scope="community")
        elif scope_param == "college":
            news_qs = news_qs.filter(scope="college")

        if user_role not in ["admin", "moderator"]:
            news_qs = news_qs.filter(
                ~Q(scope="community") |
                Q(community__is_public=True) |
                Q(community__in=user_communities)
            )
            if user_profile and user_profile.college:
                news_qs = news_qs.filter(
                    ~Q(scope="college") |
                    Q(college__iexact=user_profile.college)
                )
            else:
                news_qs = news_qs.filter(~Q(scope="college"))
        news_qs = news_qs.filter(Q(title__icontains=q) | Q(content__icontains=q))

        # 6. Events Query
        events_qs = Event.objects.filter(is_blocked=False)
        if scope_param == "community":
            events_qs = events_qs.filter(scope="community")
        elif scope_param == "college":
            events_qs = events_qs.filter(scope="college")

        if user_role not in ["admin", "moderator"]:
            events_qs = events_qs.filter(
                ~Q(scope="community") |
                Q(community__is_public=True) |
                Q(community__in=user_communities)
            )
            if user_profile and user_profile.college:
                events_qs = events_qs.filter(
                    ~Q(scope="college") |
                    Q(college__iexact=user_profile.college)
                )
            else:
                events_qs = events_qs.filter(~Q(scope="college"))
        events_qs = events_qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        # 7. Tags Query
        tags_qs = Tag.objects.filter(name__icontains=q)

        # Apply sorting
        if sort_param == "date":
            news_qs = news_qs.order_by("-created_at")
            events_qs = events_qs.order_by("-created_at")
            messages_qs = messages_qs.order_by("-created_at")

        # Specific type pagination
        if type_param == "user":
            return self._paginate_search(users_qs, NewsAuthorSerializer, "Users search retrieved.")
        elif type_param == "community":
            return self._paginate_search(communities_qs, CommunitySerializer, "Communities search retrieved.")
        elif type_param == "channel":
            return self._paginate_search(channels_qs, ChannelSerializer, "Channels search retrieved.")
        elif type_param == "message":
            return self._paginate_search(messages_qs, MessageSerializer, "Messages search retrieved.")
        elif type_param == "news":
            return self._paginate_search(news_qs, NewsSerializer, "News search retrieved.")
        elif type_param == "event":
            return self._paginate_search(events_qs, EventSerializer, "Events search retrieved.")
        elif type_param == "tag":
            return self._paginate_search(tags_qs, TagSerializer, "Tags search retrieved.")

        # Default combined response (limits top 5 results for each category)
        response_data = {
            "users": NewsAuthorSerializer(users_qs[:5], many=True, context={"request": request}).data,
            "communities": CommunitySerializer(communities_qs[:5], many=True, context={"request": request}).data,
            "channels": ChannelSerializer(channels_qs[:5], many=True, context={"request": request}).data,
            "messages": MessageSerializer(messages_qs[:5], many=True, context={"request": request}).data,
            "news": NewsSerializer(news_qs[:5], many=True, context={"request": request}).data,
            "events": EventSerializer(events_qs[:5], many=True, context={"request": request}).data,
            "tags": TagSerializer(tags_qs[:5], many=True).data,
        }

        return success_response(message="Search results retrieved.", data=response_data)

    def _paginate_search(self, queryset, serializer_cls, message) -> Response:
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = serializer_cls(page, many=True, context={"request": self.request})
            return self.get_paginated_response(serializer.data)
        serializer = serializer_cls(queryset, many=True, context={"request": self.request})
        return success_response(message=message, data=serializer.data)

    # --- Trending Searches ---

    @action(detail=False, methods=["get"])
    def trending(self, request) -> Response:
        """Get the top 5 trending search terms within the last 7 days."""
        last_week = timezone.now() - timedelta(days=7)
        trending = (
            SearchQuery.objects.filter(created_at__gte=last_week)
            .values("query")
            .annotate(count=Count("query"))
            .order_by("-count")[:5]
        )
        trending_queries = [t["query"] for t in trending]
        return success_response(message="Trending search terms retrieved.", data=trending_queries)

    # --- Suggestions ---

    @action(detail=False, methods=["get"])
    def suggestions(self, request) -> Response:
        """Get suggestions for popular communities, recommended communities, and suggested users."""
        # 1. Popular Communities (by membership count)
        popular_communities = (
            Community.objects.annotate(num_members=Count("memberships"))
            .order_by("-num_members")[:5]
        )

        # 2. Recommended Communities (public ones the user is NOT in yet)
        recommended_communities = (
            Community.objects.filter(is_public=True)
            .exclude(memberships__user=request.user)[:5]
        )

        # 3. Suggested Users (in the same college, excluding the request user)
        user_profile = getattr(request.user, "profile", None)
        suggested_users = User.objects.none()
        if user_profile and user_profile.college:
            suggested_users = (
                User.objects.filter(profile__college__iexact=user_profile.college)
                .exclude(id=request.user.id)[:5]
            )

        context = {"request": request}
        return success_response(
            message="Search suggestions retrieved.",
            data={
                "popular_communities": CommunitySerializer(popular_communities, many=True, context=context).data,
                "recommended_communities": CommunitySerializer(recommended_communities, many=True, context=context).data,
                "suggested_users": NewsAuthorSerializer(suggested_users, many=True, context=context).data,
            }
        )

    # --- Search History CRUD ---

    @action(detail=False, methods=["get", "delete"])
    def history(self, request) -> Response:
        """List or clear past search history."""
        if request.method == "DELETE":
            # Check if deleting single query or clearing all
            query_id = request.data.get("id")
            clear_all = request.data.get("clear_all", False)

            if query_id:
                query = get_object_or_404(SearchQuery, id=query_id, user=request.user)
                query.delete()
                return success_response(message="Search query deleted.")
            elif clear_all:
                SearchQuery.objects.filter(user=request.user).delete()
                return success_response(message="Search history cleared.")
            return error_response(message="Must specify 'id' or 'clear_all' = true.", status_code=status.HTTP_400_BAD_REQUEST)

        # GET history list (non-paginated)
        history_qs = SearchQuery.objects.filter(user=request.user)
        serializer = SearchQuerySerializer(history_qs, many=True)
        return success_response(message="Search history retrieved.", data=serializer.data)

    # --- Recently Visited ---

    @action(detail=False, methods=["get"], url_path="recently-visited")
    def recently_visited(self, request) -> Response:
        """Get the list of recently visited news, events, and communities."""
        visited_qs = RecentlyVisited.objects.filter(user=request.user)[:10]
        serializer = RecentlyVisitedSerializer(visited_qs, many=True)
        return success_response(message="Recently visited entities retrieved.", data=serializer.data)
