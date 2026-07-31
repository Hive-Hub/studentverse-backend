from __future__ import annotations

import asyncio
import json
import time
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserProfile
from apps.communities.models import Community, CommunityMember
from apps.news.models import Tag, News, NewsLike, NewsBookmark, NewsReport, NewsComment, NewsAttachment
from apps.news.websocket import (
    register_websocket_connection,
    unregister_websocket_connection,
    broadcast_news_published,
)
from config.asgi import application as asgi_app

User = get_user_model()


class NewsAPITests(APITestCase):
    def setUp(self):
        from unittest.mock import patch
        # Mock SupabaseStorage to prevent external requests during tests
        self.storage_save_patcher = patch('apps.accounts.storage.SupabaseStorage._save')
        self.mock_storage_save = self.storage_save_patcher.start()
        self.mock_storage_save.side_effect = lambda name, content: name

        self.storage_url_patcher = patch('apps.accounts.storage.SupabaseStorage.url')
        self.mock_storage_url = self.storage_url_patcher.start()
        self.mock_storage_url.side_effect = lambda name: f"/media/{name}"

        self.storage_exists_patcher = patch('apps.accounts.storage.SupabaseStorage.exists')
        self.mock_storage_exists = self.storage_exists_patcher.start()
        self.mock_storage_exists.return_value = False

        # Create users
        self.admin_user = User.objects.create_user(username="admin_user", email="admin@example.com", password="Password123")
        self.mod_user = User.objects.create_user(username="mod_user", email="mod@example.com", password="Password123")
        self.student_user = User.objects.create_user(username="student_user", email="student@example.com", password="Password123")
        self.other_student = User.objects.create_user(username="other_student", email="other@example.com", password="Password123")

        # Set up roles
        self.admin_profile = self.admin_user.profile
        self.admin_profile.role = UserProfile.Role.ADMIN
        self.admin_profile.college = "Engineering College"
        self.admin_profile.interests = ["technology", "hackathon"]
        self.admin_profile.save()

        self.mod_profile = self.mod_user.profile
        self.mod_profile.role = UserProfile.Role.MODERATOR
        self.mod_profile.college = "Engineering College"
        self.mod_profile.save()

        self.student_profile = self.student_user.profile
        self.student_profile.role = UserProfile.Role.STUDENT
        self.student_profile.college = "Engineering College"
        self.student_profile.interests = ["technology", "announcement"]
        self.student_profile.save()

        self.other_student_profile = self.other_student.profile
        self.other_student_profile.role = UserProfile.Role.STUDENT
        self.other_student_profile.college = "Medical College"
        self.other_student_profile.save()

        # Set up a community
        self.community = Community.objects.create(
            name="News Hackers",
            description="News hackers group",
            is_public=True
        )
        # Assign mod as moderator in community
        CommunityMember.objects.create(community=self.community, user=self.mod_user, role=CommunityMember.Role.MODERATOR)
        # Assign student as member
        CommunityMember.objects.create(community=self.community, user=self.student_user, role=CommunityMember.Role.MEMBER)

        # Base tags
        self.tag_tech = Tag.objects.create(name="technology")
        self.tag_general = Tag.objects.create(name="general")

    def tearDown(self):
        self.storage_save_patcher.stop()
        self.storage_url_patcher.stop()
        self.storage_exists_patcher.stop()

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    # --- CRUD Tests ---

    def test_create_news_permissions(self):
        # 1. Student cannot create platform news (read-only)
        self.authenticate(self.student_user)
        url = reverse("news-list")
        data = {
            "title": "Student News Attempt",
            "content": "Can I publish?",
            "category": "announcement",
            "scope": "platform",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Platform Moderator can create platform news
        self.authenticate(self.mod_user)
        data["title"] = "Mod News Title"
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["success"], True)
        self.assertEqual(response.data["data"]["title"], "Mod News Title")

    def test_scope_validation(self):
        self.authenticate(self.admin_user)
        url = reverse("news-list")

        # 1. Community scope missing community
        data = {
            "title": "Community News",
            "content": "Content...",
            "category": "technology",
            "scope": "community",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("community", response.data["errors"])

        # 2. College scope missing college
        data = {
            "title": "College News",
            "content": "Content...",
            "category": "technology",
            "scope": "college",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("college", response.data["errors"])

    def test_scheduled_publish_behavior(self):
        # Create scheduled news in the future
        future_time = timezone.now() + timedelta(days=2)
        scheduled_news = News.objects.create(
            title="Future Tech Trends",
            content="Coming soon...",
            category="technology",
            scope="platform",
            author=self.admin_user,
            status=News.Status.PUBLISHED,
            scheduled_publish_at=future_time
        )

        # 1. Student should not see it in feed
        self.authenticate(self.student_user)
        url = reverse("news-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify the list doesn't include the future scheduled news
        news_ids = [item["id"] for item in response.data["data"]]
        self.assertNotIn(scheduled_news.id, news_ids)

        # 2. Author/Admin can see it
        self.authenticate(self.admin_user)
        response = self.client.get(url)
        news_ids = [item["id"] for item in response.data["data"]]
        self.assertIn(scheduled_news.id, news_ids)

    # --- Actions: Like, Bookmark, Share, Report ---

    def test_like_bookmark_share_report(self):
        news = News.objects.create(
            title="Likeable News",
            content="Like and share!",
            category="announcement",
            scope="platform",
            author=self.admin_user,
            status=News.Status.PUBLISHED,
        )

        self.authenticate(self.student_user)

        # 1. Like
        like_url = reverse("news-like", kwargs={"pk": news.id})
        response = self.client.post(like_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["is_liked"], True)
        self.assertTrue(NewsLike.objects.filter(user=self.student_user, news=news).exists())

        # Unlike
        response = self.client.post(like_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["is_liked"], False)
        self.assertFalse(NewsLike.objects.filter(user=self.student_user, news=news).exists())

        # 2. Bookmark
        bookmark_url = reverse("news-bookmark", kwargs={"pk": news.id})
        response = self.client.post(bookmark_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["is_bookmarked"], True)

        # 3. Share
        share_url = reverse("news-share", kwargs={"pk": news.id})
        response = self.client.post(share_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["shares_count"], 1)

        # 4. Report
        report_url = reverse("news-report", kwargs={"pk": news.id})
        response = self.client.post(report_url, {"reason": "Spam content"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(NewsReport.objects.filter(user=self.student_user, news=news, reason="Spam content").exists())

    # --- Comments ---

    def test_comments_and_nested_replies(self):
        news = News.objects.create(
            title="Discussion post",
            content="Discuss below.",
            category="general",
            scope="platform",
            author=self.admin_user,
            status=News.Status.PUBLISHED,
        )

        self.authenticate(self.student_user)
        comments_url = reverse("news-comments", kwargs={"pk": news.id})

        # 1. Post top-level comment
        response = self.client.post(comments_url, {"content": "First comment!"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        parent_comment_id = response.data["data"]["id"]

        # 2. Post reply
        response = self.client.post(comments_url, {"content": "Reply comment!", "parent": parent_comment_id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        reply_comment_id = response.data["data"]["id"]

        # 3. Get comments list
        response = self.client.get(comments_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return top-level comments with replies nested inside them
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["id"], parent_comment_id)
        self.assertEqual(len(response.data["data"][0]["replies"]), 1)
        self.assertEqual(response.data["data"][0]["replies"][0]["id"], reply_comment_id)

    # --- Attachments ---

    def test_attachments_upload(self):
        news = News.objects.create(
            title="Documented news",
            content="Look at attachments.",
            category="announcement",
            scope="platform",
            author=self.admin_user,
            status=News.Status.PUBLISHED,
        )

        self.authenticate(self.admin_user)
        url = reverse("news-attachments", kwargs={"pk": news.id})

        file1 = SimpleUploadedFile("resume.pdf", b"pdf content", content_type="application/pdf")
        file2 = SimpleUploadedFile("image.png", b"image content", content_type="image/png")

        response = self.client.post(url, {"files": [file1, file2]}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["data"]), 2)
        self.assertTrue(NewsAttachment.objects.filter(news=news, file_name="resume.pdf").exists())

    # --- Moderation Queue & Action ---

    def test_moderation_flow(self):
        news = News.objects.create(
            title="Flagged News",
            content="Bad words.",
            category="announcement",
            scope="platform",
            author=self.student_user,
            status=News.Status.PUBLISHED,
        )

        # Report the news
        self.authenticate(self.other_student)
        self.client.post(reverse("news-report", kwargs={"pk": news.id}), {"reason": "bad words"})

        # 1. Student cannot access moderation queue
        response = self.client.get(reverse("news-moderation-queue"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Admin can access moderation queue
        self.authenticate(self.admin_user)
        response = self.client.get(reverse("news-moderation-queue"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["id"], news.id)

        # 3. Admin blocks news
        mod_url = reverse("news-moderate", kwargs={"pk": news.id})
        response = self.client.post(mod_url, {"action": "block"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        news.refresh_from_db()
        self.assertTrue(news.is_blocked)

        # Verify blocked news is hidden from student feeds
        self.authenticate(self.student_user)
        response = self.client.get(reverse("news-list"))
        news_ids = [item["id"] for item in response.data["data"]]
        self.assertNotIn(news.id, news_ids)

    # --- Custom Feeds (Trending, Recommended, College, Community) ---

    def test_trending_feed(self):
        # Create news items
        news1 = News.objects.create(title="Post One", content="Content", category="tech", scope="platform", author=self.admin_user, status=News.Status.PUBLISHED)
        news2 = News.objects.create(title="Post Two", content="Content", category="tech", scope="platform", author=self.admin_user, status=News.Status.PUBLISHED)

        # news1 has 1 like, 1 comment
        NewsLike.objects.create(user=self.student_user, news=news1)
        NewsComment.objects.create(user=self.student_user, news=news1, content="nice")

        # news2 has no activity
        self.authenticate(self.student_user)
        response = self.client.get(reverse("news-trending"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # news1 should be first because it has a higher trending score
        self.assertEqual(response.data["data"][0]["id"], news1.id)
        self.assertEqual(response.data["data"][1]["id"], news2.id)

    def test_college_feed(self):
        # news1: Engineering College
        news1 = News.objects.create(
            title="Engineering News", content="Content", category="announcement",
            scope="college", college="Engineering College", author=self.admin_user, status=News.Status.PUBLISHED
        )
        # news2: Medical College
        news2 = News.objects.create(
            title="Medical News", content="Content", category="announcement",
            scope="college", college="Medical College", author=self.admin_user, status=News.Status.PUBLISHED
        )

        # Student user is in Engineering College
        self.authenticate(self.student_user)
        response = self.client.get(reverse("news-college"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see only Engineering News
        news_ids = [item["id"] for item in response.data["data"]]
        self.assertIn(news1.id, news_ids)
        self.assertNotIn(news2.id, news_ids)


class WebSocketTests(TransactionTestCase):
    async def test_websocket_news_route(self):
        # Verify custom ASGI routing for /ws/news/
        connected = asyncio.Event()
        disconnected = asyncio.Event()
        received_events = []

        async def mock_send(event):
            received_events.append(event)
            if event["type"] == "websocket.accept":
                connected.set()

        async def mock_receive():
            await connected.wait()
            disconnected.set()
            return {"type": "websocket.disconnect"}

        scope = {
            "type": "websocket",
            "path": "/ws/news/",
        }

        task = asyncio.create_task(asgi_app(scope, mock_receive, mock_send))
        await asyncio.wait_for(disconnected.wait(), timeout=3.0)
        await task

        self.assertTrue(connected.is_set())
        self.assertEqual(received_events[0]["type"], "websocket.accept")

    def test_websocket_broadcast(self):
        # Register a mock connection and broadcast a publication update
        received_messages = []

        async def mock_send(message):
            received_messages.append(message)

        register_websocket_connection(mock_send)
        try:
            news_data = {"id": 99, "title": "Breaking News!"}
            broadcast_news_published(news_data)

            # Wait a brief moment for the daemon thread
            time.sleep(0.3)

            self.assertEqual(len(received_messages), 1)
            payload = json.loads(received_messages[0]["text"])
            self.assertEqual(payload["event"], "news_published")
            self.assertEqual(payload["data"]["title"], "Breaking News!")
        finally:
            unregister_websocket_connection(mock_send)
