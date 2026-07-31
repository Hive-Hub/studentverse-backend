from __future__ import annotations

from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserProfile
from apps.communities.models import Community
from apps.news.models import News, Tag
from apps.events.models import Event
from apps.search.models import SearchQuery, RecentlyVisited

User = get_user_model()


class SearchAPITests(APITestCase):
    def setUp(self):
        # Mock SupabaseStorage to isolate tests from real storage requests
        self.storage_save_patcher = patch('apps.accounts.storage.SupabaseStorage._save')
        self.mock_storage_save = self.storage_save_patcher.start()
        self.mock_storage_save.side_effect = lambda name, content: name

        self.storage_url_patcher = patch('apps.accounts.storage.SupabaseStorage.url')
        self.mock_storage_url = self.storage_url_patcher.start()
        self.mock_storage_url.side_effect = lambda name: f"/media/{name}"

        self.storage_exists_patcher = patch('apps.accounts.storage.SupabaseStorage.exists')
        self.mock_storage_exists = self.storage_exists_patcher.start()
        self.mock_storage_exists.return_value = False

        # Create test users
        self.user1 = User.objects.create_user(username="alpha_student", email="alpha@example.com", password="Password123")
        self.user2 = User.objects.create_user(username="beta_student", email="beta@example.com", password="Password123")

        self.p1 = self.user1.profile
        self.p1.college = "Engineering College"
        self.p1.save()

        self.p2 = self.user2.profile
        self.p2.college = "Engineering College"
        self.p2.save()

        # Create search entities
        self.community = Community.objects.create(
            name="Testing Community",
            description="All about test items",
            is_public=True
        )
        self.tag = Tag.objects.create(name="testtag")
        
        self.news = News.objects.create(
            title="Testing News",
            content="Some details about tests",
            scope="platform",
            author=self.user1,
            status=News.Status.PUBLISHED
        )
        self.news.tags.add(self.tag)

        self.event = Event.objects.create(
            title="Testing Event",
            description="Event for testing",
            scope="platform",
            event_type="online",
            start_time=timezone_now() + timedelta_days(1),
            end_time=timezone_now() + timedelta_days(1, hours=2),
            author=self.user1
        )

    def tearDown(self):
        self.storage_save_patcher.stop()
        self.storage_url_patcher.stop()
        self.storage_exists_patcher.stop()

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    # --- Combined and Specific Search ---

    def test_global_search_combined_and_specific(self):
        self.authenticate(self.user1)

        # 1. Combined Global Search
        url = reverse("search-query")
        response = self.client.get(url, {"q": "Testing"})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["success"], True)
        
        # Verify matching sections contain our items
        self.assertGreater(len(response.data["data"]["communities"]), 0)
        self.assertGreater(len(response.data["data"]["news"]), 0)
        self.assertGreater(len(response.data["data"]["events"]), 0)

        # Verify search query is logged in DB
        self.assertTrue(SearchQuery.objects.filter(user=self.user1, query="Testing").exists())

        # 2. Specific type search (returns DRF standard pagination)
        response = self.client.get(url, {"q": "Testing", "type": "news"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)  # checks pagination block
        self.assertEqual(len(response.data["results"]), 1)

    # --- Trending Queries ---

    def test_trending_searches(self):
        # Generate some queries
        SearchQuery.objects.create(user=self.user1, query="react")
        SearchQuery.objects.create(user=self.user2, query="react")
        SearchQuery.objects.create(user=self.user1, query="django")

        self.authenticate(self.user1)
        url = reverse("search-trending")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"][0], "react")
        self.assertEqual(response.data["data"][1], "django")

    # --- Suggestions ---

    def test_suggestions(self):
        self.authenticate(self.user1)
        url = reverse("search-suggestions")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("popular_communities", response.data["data"])
        self.assertIn("recommended_communities", response.data["data"])
        self.assertIn("suggested_users", response.data["data"])

    # --- Search History CRUD ---

    def test_search_history_crud(self):
        self.authenticate(self.user1)
        sq1 = SearchQuery.objects.create(user=self.user1, query="react")
        sq2 = SearchQuery.objects.create(user=self.user1, query="django")

        url = reverse("search-history")
        
        # GET history list
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 2)

        # DELETE single query
        response = self.client.delete(url, {"id": sq1.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(SearchQuery.objects.filter(id=sq1.id).exists())

        # Clear all history
        response = self.client.delete(url, {"clear_all": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(SearchQuery.objects.filter(user=self.user1).count(), 0)

    # --- Recently Visited Logging ---

    def test_recently_visited_logging(self):
        self.authenticate(self.user1)
        
        # Access details of community, news, and event to trigger logging
        detail_news_url = reverse("news-detail", kwargs={"pk": self.news.id})
        self.client.get(detail_news_url)

        detail_event_url = reverse("events-detail", kwargs={"pk": self.event.id})
        self.client.get(detail_event_url)

        detail_comm_url = reverse("communities-detail", kwargs={"slug": self.community.slug})
        self.client.get(detail_comm_url)

        # Fetch recently visited
        url = reverse("search-recently-visited")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 3)
        # Order should be community (most recent), then event, then news
        self.assertEqual(response.data["data"][0]["entity_type"], "community")
        self.assertEqual(response.data["data"][1]["entity_type"], "event")
        self.assertEqual(response.data["data"][2]["entity_type"], "news")


# Helper datetime wrappers
def timezone_now():
    from django.utils import timezone
    return timezone.now()

def timedelta_days(days, hours=0):
    from datetime import timedelta
    return timedelta(days=days, hours=hours)
