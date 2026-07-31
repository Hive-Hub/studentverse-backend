from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.common.responses import error_response, success_response
from apps.communities.models import Community, CommunityMember, Channel
from apps.events.models import Event
from apps.news.models import News

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom throttle classes
# ---------------------------------------------------------------------------

class PublicHighRateThrottle(AnonRateThrottle):
    """60 requests/minute — used on low-cost overview endpoints."""
    scope = "public_high"


class PublicLowRateThrottle(AnonRateThrottle):
    """30 requests/minute — used on per-resource endpoints."""
    scope = "public_low"


# ---------------------------------------------------------------------------
# 1. Platform Statistics
# ---------------------------------------------------------------------------

@method_decorator(cache_page(60 * 5), name="dispatch")
class PlatformStatsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicHighRateThrottle]

    def get(self, request):
        data = {
            "users": User.objects.count(),
            "communities": Community.objects.count(),
            "channels": Channel.objects.count(),
            "news_articles": News.objects.count(),
            "events": Event.objects.count(),
        }
        return success_response(data=data, message="Platform statistics retrieved.")


# ---------------------------------------------------------------------------
# 2. Trending Communities
# ---------------------------------------------------------------------------

@method_decorator(cache_page(60 * 5), name="dispatch")
class TrendingCommunitiesView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicHighRateThrottle]

    def get(self, request):
        communities = (
            Community.objects.filter(is_public=True)
            .annotate(member_count=Count("members", distinct=True))
            .order_by("-member_count")[:10]
        )
        data = [
            {
                "id": c.id,
                "name": c.name,
                "slug": c.slug,
                "description": c.description,
                "icon": str(c.icon.url) if c.icon else None,
                "banner": str(c.banner.url) if c.banner else None,
                "member_count": c.member_count,
            }
            for c in communities
        ]
        return success_response(data=data, message="Trending communities retrieved.")


# ---------------------------------------------------------------------------
# 3. Featured News
# ---------------------------------------------------------------------------

@method_decorator(cache_page(60 * 5), name="dispatch")
class FeaturedNewsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicHighRateThrottle]

    def get(self, request):
        articles = (
            News.objects.filter(status=News.Status.PUBLISHED)
            .select_related("author", "community")
            .order_by("-created_at")[:10]
        )
        data = [
            {
                "id": n.id,
                "title": n.title,
                "category": n.category,
                "image": str(n.image.url) if n.image else None,
                "author": {"id": n.author.id, "username": n.author.username} if n.author else None,
                "community": {"name": n.community.name, "slug": n.community.slug} if n.community else None,
                "published_at": n.created_at.isoformat(),
                "likes_count": n.likes.count() if hasattr(n, "likes") else 0,
            }
            for n in articles
        ]
        return success_response(data=data, message="Featured news retrieved.")


# ---------------------------------------------------------------------------
# 4. Upcoming Events
# ---------------------------------------------------------------------------

@method_decorator(cache_page(60 * 5), name="dispatch")
class UpcomingEventsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicHighRateThrottle]

    def get(self, request):
        now = timezone.now()
        events = (
            Event.objects.filter(start_time__gt=now)
            .select_related("community", "author")
            .order_by("start_time")[:10]
        )
        data = [
            {
                "id": e.id,
                "title": e.title,
                "description": e.description[:200] if e.description else "",
                "start_datetime": e.start_time.isoformat(),
                "end_datetime": e.end_time.isoformat() if e.end_time else None,
                "location": e.location,
                "event_type": e.event_type,
                "community": {"name": e.community.name, "slug": e.community.slug} if e.community else None,
                "author": {"username": e.author.username} if e.author else None,
                "banner": str(e.banner.url) if e.banner else None,
            }
            for e in events
        ]
        return success_response(data=data, message="Upcoming events retrieved.")


# ---------------------------------------------------------------------------
# 5. Community Statistics (per slug)
# ---------------------------------------------------------------------------

@method_decorator(cache_page(60 * 2), name="dispatch")
class CommunityStatsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicLowRateThrottle]

    def get(self, request, slug):
        try:
            community = Community.objects.get(slug=slug, is_public=True)
        except Community.DoesNotExist:
            return error_response(message="Community not found.", status_code=404)

        now = timezone.now()
        data = {
            "id": community.id,
            "name": community.name,
            "slug": community.slug,
            "description": community.description,
            "member_count": CommunityMember.objects.filter(community=community).count(),
            "channel_count": Channel.objects.filter(community=community).count(),
            "news_count": News.objects.filter(community=community, status=News.Status.PUBLISHED).count(),
            "event_count": Event.objects.filter(community=community).count(),
            "upcoming_events": Event.objects.filter(community=community, start_time__gt=now).count(),
            "created_at": community.created_at.isoformat(),
        }
        return success_response(data=data, message="Community statistics retrieved.")


# ---------------------------------------------------------------------------
# 6. Public User Profile
# ---------------------------------------------------------------------------

@method_decorator(cache_page(60 * 2), name="dispatch")
class PublicProfileView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicLowRateThrottle]

    def get(self, request, username):
        try:
            user = User.objects.select_related("profile").get(username__iexact=username)
        except User.DoesNotExist:
            return error_response(message="User not found.", status_code=404)

        profile = getattr(user, "profile", None)
        data = {
            "id": user.id,
            "username": user.username,
            "display_name": profile.display_name if profile else "",
            "bio": profile.bio if profile else "",
            "college": profile.college if profile else "",
            "branch": profile.branch if profile else "",
            "year": profile.year if profile else None,
            "skills": profile.skills if profile else [],
            "interests": profile.interests if profile else [],
            "github": profile.github if profile else None,
            "linkedin": profile.linkedin if profile else None,
            "portfolio": profile.portfolio if profile else None,
            "location": profile.location if profile else "",
            "is_verified_author": profile.is_verified_author if profile else False,
            "profile_photo": str(profile.profile_photo.url) if profile and profile.profile_photo else None,
            "joined": user.date_joined.isoformat(),
        }
        return success_response(data=data, message="Public profile retrieved.")


# ---------------------------------------------------------------------------
# 7–9. SEO Metadata
# ---------------------------------------------------------------------------

@method_decorator(cache_page(60 * 10), name="dispatch")
class SeoCommunitView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicLowRateThrottle]

    def get(self, request, slug):
        try:
            c = Community.objects.get(slug=slug, is_public=True)
        except Community.DoesNotExist:
            return error_response(message="Community not found.", status_code=404)

        data = {
            "title": f"{c.name} — StudentVerse Community",
            "description": c.description[:160] if c.description else f"Join {c.name} on StudentVerse.",
            "canonical_url": f"/communities/{c.slug}/",
            "robots": "index, follow",
            "keywords": [c.name, "student community", "college"],
        }
        return success_response(data=data, message="SEO metadata retrieved.")


@method_decorator(cache_page(60 * 10), name="dispatch")
class SeoNewsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicLowRateThrottle]

    def get(self, request, news_id):
        try:
            n = News.objects.select_related("author").get(pk=news_id, status=News.Status.PUBLISHED)
        except News.DoesNotExist:
            return error_response(message="News article not found.", status_code=404)

        data = {
            "title": f"{n.title} — StudentVerse",
            "description": n.content[:160],
            "canonical_url": f"/news/{n.id}/",
            "robots": "index, follow",
            "author": n.author.get_full_name() or n.author.username if n.author else "StudentVerse",
            "published_time": n.created_at.isoformat(),
        }
        return success_response(data=data, message="SEO metadata retrieved.")


@method_decorator(cache_page(60 * 10), name="dispatch")
class SeoEventView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicLowRateThrottle]

    def get(self, request, pk):
        try:
            e = Event.objects.select_related("community").get(pk=pk)
        except Event.DoesNotExist:
            return error_response(message="Event not found.", status_code=404)

        data = {
            "title": f"{e.title} — StudentVerse Event",
            "description": e.description[:160] if e.description else e.title,
            "canonical_url": f"/events/{e.id}/",
            "robots": "index, follow",
            "start_date": e.start_time.isoformat(),
        }
        return success_response(data=data, message="SEO metadata retrieved.")


# ---------------------------------------------------------------------------
# 10–11. Open Graph Data
# ---------------------------------------------------------------------------

@method_decorator(cache_page(60 * 10), name="dispatch")
class OgCommunityView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicLowRateThrottle]

    def get(self, request, slug):
        try:
            c = Community.objects.get(slug=slug, is_public=True)
        except Community.DoesNotExist:
            return error_response(message="Community not found.", status_code=404)

        data = {
            "og:type": "website",
            "og:title": f"{c.name} — StudentVerse",
            "og:description": c.description[:200] if c.description else f"Join {c.name} on StudentVerse.",
            "og:image": str(c.banner.url) if c.banner else None,
            "og:url": f"/communities/{c.slug}/",
            "og:site_name": "StudentVerse",
        }
        return success_response(data=data, message="Open Graph data retrieved.")


@method_decorator(cache_page(60 * 10), name="dispatch")
class OgNewsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicLowRateThrottle]

    def get(self, request, news_id):
        try:
            n = News.objects.select_related("author").get(pk=news_id, status=News.Status.PUBLISHED)
        except News.DoesNotExist:
            return error_response(message="News article not found.", status_code=404)

        data = {
            "og:type": "article",
            "og:title": n.title,
            "og:description": n.content[:200],
            "og:image": str(n.image.url) if n.image else None,
            "og:url": f"/news/{n.id}/",
            "og:site_name": "StudentVerse",
            "article:author": n.author.username if n.author else None,
            "article:published_time": n.created_at.isoformat(),
        }
        return success_response(data=data, message="Open Graph data retrieved.")
