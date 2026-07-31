from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.communities.models import Community, CommunityMember
from apps.events.models import Event
from apps.news.models import News

User = get_user_model()

# Use a fast dummy cache for tests so cache_page doesn't interfere
DUMMY_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}


@override_settings(CACHES=DUMMY_CACHE)
class PublicAPITests(APITestCase):
    def setUp(self):
        # Author user
        self.author = User.objects.create_user(
            username="pub_author", email="pub@example.com", password="Test1234"
        )
        self.author.profile.bio = "A test bio"
        self.author.profile.skills = ["Python", "Django"]
        self.author.profile.save()

        # Community
        self.community = Community.objects.create(
            name="Public Community",
            slug="public-community",
            description="Open to all students",
            is_public=True,
        )
        CommunityMember.objects.create(
            community=self.community, user=self.author, role=CommunityMember.Role.OWNER
        )

        # News
        self.news = News.objects.create(
            title="Big Announcement",
            content="Full content here",
            category="announcement",
            community=self.community,
            author=self.author,
            status=News.Status.PUBLISHED,
        )

        # Event (future)
        self.event = Event.objects.create(
            title="Tech Meetup",
            description="Come join us",
            community=self.community,
            author=self.author,
            start_time=timezone.now() + timezone.timedelta(days=5),
            end_time=timezone.now() + timezone.timedelta(days=5, hours=2),
            location="Main Hall",
            event_type=Event.EventType.OFFLINE,
        )

    # -----------------------------------------------------------------------
    # Platform Stats
    # -----------------------------------------------------------------------
    def test_platform_stats_no_auth(self):
        url = reverse("public-platform-stats")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIn("users", data)
        self.assertIn("communities", data)
        self.assertIn("news_articles", data)
        self.assertIn("events", data)
        self.assertGreaterEqual(data["communities"], 1)

    # -----------------------------------------------------------------------
    # Trending Communities
    # -----------------------------------------------------------------------
    def test_trending_communities_no_auth(self):
        url = reverse("public-trending-communities")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["data"]), 1)
        self.assertIn("member_count", response.data["data"][0])

    # -----------------------------------------------------------------------
    # Featured News
    # -----------------------------------------------------------------------
    def test_featured_news_no_auth(self):
        url = reverse("public-featured-news")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        articles = response.data["data"]
        self.assertGreaterEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Big Announcement")

    # -----------------------------------------------------------------------
    # Upcoming Events
    # -----------------------------------------------------------------------
    def test_upcoming_events_no_auth(self):
        url = reverse("public-upcoming-events")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        events = response.data["data"]
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "Tech Meetup")

    # -----------------------------------------------------------------------
    # Community Stats
    # -----------------------------------------------------------------------
    def test_community_stats_no_auth(self):
        url = reverse("public-community-stats", kwargs={"slug": self.community.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["slug"], "public-community")
        self.assertEqual(data["member_count"], 1)
        self.assertIn("news_count", data)

    def test_community_stats_private_not_found(self):
        private = Community.objects.create(
            name="Private", slug="private-com", description="", is_public=False
        )
        url = reverse("public-community-stats", kwargs={"slug": private.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # -----------------------------------------------------------------------
    # Public Profile
    # -----------------------------------------------------------------------
    def test_public_profile_no_auth(self):
        url = reverse("public-profile", kwargs={"username": self.author.username})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["username"], self.author.username)
        self.assertIn("bio", data)
        self.assertIn("skills", data)

    def test_public_profile_not_found(self):
        url = reverse("public-profile", kwargs={"username": "nonexistentuser"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # -----------------------------------------------------------------------
    # SEO Endpoints
    # -----------------------------------------------------------------------
    def test_seo_community(self):
        url = reverse("public-seo-community", kwargs={"slug": self.community.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIn("title", data)
        self.assertIn("description", data)
        self.assertIn("canonical_url", data)
        self.assertIn("robots", data)

    def test_seo_news(self):
        url = reverse("public-seo-news", kwargs={"news_id": self.news.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIn("title", data)
        self.assertIn("published_time", data)

    def test_seo_event(self):
        url = reverse("public-seo-event", kwargs={"pk": self.event.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIn("title", data)
        self.assertIn("start_date", data)

    # -----------------------------------------------------------------------
    # Open Graph Endpoints
    # -----------------------------------------------------------------------
    def test_og_community(self):
        url = reverse("public-og-community", kwargs={"slug": self.community.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["og:type"], "website")
        self.assertIn("og:title", data)
        self.assertIn("og:description", data)

    def test_og_news(self):
        url = reverse("public-og-news", kwargs={"news_id": self.news.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["og:type"], "article")
        self.assertIn("og:title", data)
        self.assertIn("article:published_time", data)

    # -----------------------------------------------------------------------
    # 404 cases
    # -----------------------------------------------------------------------
    def test_seo_community_not_found(self):
        url = reverse("public-seo-community", kwargs={"slug": "no-such-community"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_og_news_not_found(self):
        url = reverse("public-og-news", kwargs={"news_id": 999999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
