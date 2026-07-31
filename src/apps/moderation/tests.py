from __future__ import annotations

import json
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITransactionTestCase
from apps.communities.models import Community, CommunityMember, Channel
from apps.messaging.models import Message
from apps.moderation.models import Report, UserMute, CommunityBan, BlockedWord, MessageAuditLog

User = get_user_model()


class ModerationAPITests(APITransactionTestCase):
    def setUp(self):
        # Create test users
        self.admin = User.objects.create_user(username="admin", email="admin@example.com", password="Password123")
        self.admin.profile.role = "admin"
        self.admin.profile.save()

        self.moderator = User.objects.create_user(username="moderator", email="moderator@example.com", password="Password123")
        self.moderator.profile.role = "moderator"
        self.moderator.profile.save()

        self.user1 = User.objects.create_user(username="user1", email="user1@example.com", password="Password123")
        self.user2 = User.objects.create_user(username="user2", email="user2@example.com", password="Password123")

        # Create community
        self.community = Community.objects.create(
            name="Testing Community",
            slug="testing-community",
            description="Testing description",
            is_public=True,
        )
        self.membership_user1 = CommunityMember.objects.create(
            community=self.community,
            user=self.user1,
            role=CommunityMember.Role.OWNER,
        )
        self.membership_user2 = CommunityMember.objects.create(
            community=self.community,
            user=self.user2,
            role=CommunityMember.Role.MEMBER,
        )

        self.channel = Channel.objects.create(
            community=self.community,
            name="General",
            description="General discussion",
            permission_type="public",
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    # --- Reports Tests ---

    def test_submit_report_and_resolve(self):
        # Report user2 as user1
        self.authenticate(self.user1)
        url = reverse("report-list")
        data = {
            "report_type": "user",
            "target_id": str(self.user2.id),
            "reason": "Harassment",
            "details": "User is calling me names.",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["reason"], "Harassment")

        report_id = response.data["data"]["id"]

        # Try to retrieve reports as user2 (should fail)
        self.authenticate(self.user2)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Retrieve as Platform Moderator (should succeed)
        self.authenticate(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)

        # Resolve report
        detail_url = reverse("report-detail", kwargs={"pk": report_id})
        patch_data = {
            "status": "reviewed",
            "moderator_notes": "Reviewed and warned the user.",
        }
        response = self.client.patch(detail_url, patch_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["status"], "reviewed")
        self.assertEqual(response.data["data"]["moderator_notes"], "Reviewed and warned the user.")

    # --- Mute Tests ---

    def test_mute_and_unmute_workflows(self):
        # Mute user2 inside community as owner user1
        self.authenticate(self.user1)
        url = reverse("moderation-mute")
        data = {
            "user_id": self.user2.id,
            "community_id": self.community.id,
            "duration_minutes": 10,
            "reason": "Spamming emojis",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify user2 is blocked from writing messages in that community's channel
        self.authenticate(self.user2)
        msg_url = reverse("message-list", kwargs={"channel_id": self.channel.id})
        msg_data = {"content": "Hello world"}
        response = self.client.post(msg_url, msg_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("muted", response.data["message"])

        # Unmute user2 inside community
        self.authenticate(self.user1)
        unmute_url = reverse("moderation-unmute")
        unmute_data = {
            "user_id": self.user2.id,
            "community_id": self.community.id,
        }
        response = self.client.post(unmute_url, unmute_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify user2 can post again
        self.authenticate(self.user2)
        response = self.client.post(msg_url, msg_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # --- Kick & Ban Tests ---

    def test_kick_member_flow(self):
        # Kick user2
        self.authenticate(self.user1)
        url = reverse("moderation-kick")
        data = {
            "user_id": self.user2.id,
            "community_id": self.community.id,
            "reason": "Not active",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check user2 is no longer a member
        self.assertFalse(CommunityMember.objects.filter(community=self.community, user=self.user2).exists())

    def test_ban_and_unban_flow(self):
        # Ban user2
        self.authenticate(self.user1)
        url = reverse("moderation-ban")
        data = {
            "user_id": self.user2.id,
            "community_id": self.community.id,
            "ban_type": "permanent",
            "reason": "Trolling",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify member was kicked
        self.assertFalse(CommunityMember.objects.filter(community=self.community, user=self.user2).exists())

        # Verify user2 cannot join again
        self.authenticate(self.user2)
        join_url = reverse("community-join", kwargs={"slug": self.community.slug})
        response = self.client.post(join_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("banned", response.data["message"])

        # Unban user2
        self.authenticate(self.user1)
        unban_url = reverse("moderation-unban")
        unban_data = {
            "user_id": self.user2.id,
            "community_id": self.community.id,
        }
        response = self.client.post(unban_url, unban_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify user2 can join now
        self.authenticate(self.user2)
        response = self.client.post(join_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # --- Blocked Words & Content Filters Tests ---

    def test_blocked_words_crud_and_filtering(self):
        # Register blocked word
        self.authenticate(self.admin)
        url = reverse("blocked-word-list")
        response = self.client.post(url, {"word": "AbusiveWord"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["word"], "abusiveword")

        # Verify user1 cannot send a message containing this blocked word
        self.authenticate(self.user1)
        msg_url = reverse("message-list", kwargs={"channel_id": self.channel.id})
        msg_data = {"content": "Check this abusiveword!!!"}
        response = self.client.post(msg_url, msg_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("blocked words", response.data["message"])

    def test_spam_detection_and_rate_limit(self):
        import os
        os.environ["DISABLE_RATE_LIMIT"] = "false"
        try:
            self.authenticate(self.user1)
            msg_url = reverse("message-list", kwargs={"channel_id": self.channel.id})
            
            # We need to simulate distinct messages but check that rapid-fire rate limit triggers (max 1 per second REST API)
            response1 = self.client.post(msg_url, {"content": "Rapid message 1"})
            self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

            response2 = self.client.post(msg_url, {"content": "Rapid message 2"})
            # Should hit the rate limit constraint (< 1 second interval)
            self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("Rate limit exceeded", response2.data["message"])
        finally:
            os.environ["DISABLE_RATE_LIMIT"] = "true"

    # --- Audit Logs Tests ---

    def test_message_audit_logs(self):
        self.authenticate(self.user1)
        msg_url = reverse("message-list", kwargs={"channel_id": self.channel.id})
        
        # Create message (triggers creation audit log)
        response = self.client.post(msg_url, {"content": "Original message content"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        msg_id = response.data["data"]["id"]

        # Wait to bypass rate limit
        import time
        # Or mock timezone.now to bypass rate limiting during edits
        from unittest.mock import patch
        from django.utils import timezone
        
        with patch("django.utils.timezone.now") as mock_now:
            mock_now.return_value = timezone.now() + timezone.timedelta(seconds=5)
            
            # Edit message (triggers edit audit log)
            detail_url = reverse("message-detail", kwargs={"channel_id": self.channel.id, "pk": msg_id})
            response = self.client.patch(detail_url, {"content": "Edited message content"})
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Delete message (triggers delete audit log)
            response = self.client.delete(detail_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Retrieve audit logs as Platform Moderator
        self.authenticate(self.moderator)
        audit_url = reverse("moderation-audit-logs")
        response = self.client.get(audit_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Ensure we have logs
        self.assertTrue(len(response.data["data"]) >= 3)
        actions = [log["action"] for log in response.data["data"]]
        self.assertIn("created", actions)
        self.assertIn("edited", actions)
        self.assertIn("deleted", actions)

    # --- Dashboard Stats Test ---

    def test_admin_dashboard_stats(self):
        self.authenticate(self.moderator)
        url = reverse("moderation-dashboard-stats")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_reports", response.data["data"])
        self.assertIn("active_bans", response.data["data"])
        self.assertIn("active_mutes", response.data["data"])
