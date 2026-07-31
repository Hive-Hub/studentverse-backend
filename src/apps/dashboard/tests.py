from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITransactionTestCase

from apps.communities.models import Community, CommunityMember, Channel
from apps.dashboard.models import Announcement, PlatformSetting
from apps.moderation.models import Report

User = get_user_model()


class DashboardAPITests(APITransactionTestCase):
    def setUp(self):
        # Create platform admin
        self.admin = User.objects.create_user(
            username="admin_dash", email="admin_dash@example.com", password="Password123"
        )
        self.admin.profile.role = "admin"
        self.admin.profile.save()

        # Create platform moderator
        self.moderator = User.objects.create_user(
            username="mod_dash", email="mod_dash@example.com", password="Password123"
        )
        self.moderator.profile.role = "moderator"
        self.moderator.profile.save()

        # Create regular user
        self.user = User.objects.create_user(
            username="regular_dash", email="regular_dash@example.com", password="Password123"
        )

        # Create community and channel
        self.community = Community.objects.create(
            name="Dash Community", slug="dash-community", description="Test", is_public=True
        )
        CommunityMember.objects.create(
            community=self.community, user=self.admin, role=CommunityMember.Role.OWNER
        )
        self.channel = Channel.objects.create(
            community=self.community, name="General", description="Test", permission_type="public"
        )

        # Create a report
        Report.objects.create(
            reporter=self.user,
            report_type="user",
            target_id=str(self.admin.id),
            reason="Spam",
            status="pending",
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    # -------------------------------------------------------------------
    # Overview Stats
    # -------------------------------------------------------------------

    def test_overview_stats_admin(self):
        self.authenticate(self.admin)
        url = reverse("dashboard-overview")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIn("users", data)
        self.assertIn("communities", data)
        self.assertIn("channels", data)
        self.assertIn("messages", data)
        self.assertIn("news", data)
        self.assertIn("events", data)
        self.assertIn("pending_reports", data)
        self.assertEqual(data["pending_reports"], 1)

    def test_overview_stats_moderator(self):
        self.authenticate(self.moderator)
        url = reverse("dashboard-overview")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_overview_stats_regular_user_denied(self):
        self.authenticate(self.user)
        url = reverse("dashboard-overview")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------
    # User Stats
    # -------------------------------------------------------------------

    def test_user_stats_admin(self):
        self.authenticate(self.admin)
        url = reverse("dashboard-user-stats")
        response = self.client.get(url, {"days": 30})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIn("total_users", data)
        self.assertIn("role_breakdown", data)
        self.assertIn("top_active_users", data)
        self.assertIn("daily_growth", data)

    def test_user_stats_moderator_denied(self):
        self.authenticate(self.moderator)
        url = reverse("dashboard-user-stats")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------
    # Content Stats
    # -------------------------------------------------------------------

    def test_content_stats(self):
        self.authenticate(self.moderator)
        url = reverse("dashboard-content-stats")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIn("total_messages", data)
        self.assertIn("total_news", data)
        self.assertIn("total_events", data)

    # -------------------------------------------------------------------
    # Storage Stats
    # -------------------------------------------------------------------

    def test_storage_stats_admin(self):
        self.authenticate(self.admin)
        url = reverse("dashboard-storage-stats")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIn("total_bytes_used", data)
        self.assertIn("top_uploaders", data)

    def test_storage_stats_moderator_denied(self):
        self.authenticate(self.moderator)
        url = reverse("dashboard-storage-stats")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------
    # Moderation Queue
    # -------------------------------------------------------------------

    def test_moderation_queue_admin(self):
        self.authenticate(self.admin)
        url = reverse("dashboard-moderation-queue")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["reason"], "Spam")

    def test_moderation_queue_moderator(self):
        self.authenticate(self.moderator)
        url = reverse("dashboard-moderation-queue")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_moderation_queue_user_denied(self):
        self.authenticate(self.user)
        url = reverse("dashboard-moderation-queue")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------
    # System Health
    # -------------------------------------------------------------------

    def test_system_health_admin(self):
        self.authenticate(self.admin)
        url = reverse("dashboard-health")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIn("database", data)
        self.assertIn("overall", data)
        self.assertEqual(data["database"]["status"], "ok")

    def test_system_health_moderator_denied(self):
        self.authenticate(self.moderator)
        url = reverse("dashboard-health")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------
    # API Usage
    # -------------------------------------------------------------------

    def test_api_usage_admin(self):
        self.authenticate(self.admin)
        url = reverse("dashboard-api-usage")
        response = self.client.get(url, {"hours": 24})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIn("total_requests", data)
        self.assertIn("top_endpoints", data)

    # -------------------------------------------------------------------
    # Audit Logs
    # -------------------------------------------------------------------

    def test_audit_logs_admin(self):
        self.authenticate(self.admin)
        url = reverse("dashboard-audit-logs")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("meta", response.data)

    def test_audit_logs_moderator(self):
        self.authenticate(self.moderator)
        url = reverse("dashboard-audit-logs")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # -------------------------------------------------------------------
    # Announcements
    # -------------------------------------------------------------------

    def test_announcement_crud(self):
        self.authenticate(self.admin)
        list_url = reverse("dashboard-announcements")

        # Create
        create_data = {
            "title": "Maintenance tonight",
            "body": "Platform will be offline 2-4 AM.",
            "level": "warning",
        }
        response = self.client.post(list_url, create_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ann_id = response.data["data"]["id"]
        self.assertEqual(response.data["data"]["level"], "warning")

        # List
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)

        # Retrieve
        detail_url = reverse("dashboard-announcement-detail", kwargs={"pk": ann_id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Update (deactivate)
        response = self.client.patch(detail_url, {"is_active": False})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["data"]["is_active"])

        # Delete
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Announcement.objects.count(), 0)

    def test_announcement_list_moderator(self):
        """Moderator can view announcements but not create/delete."""
        self.authenticate(self.admin)
        self.client.post(
            reverse("dashboard-announcements"),
            {"title": "Test", "body": "Body", "level": "info"},
        )

        self.authenticate(self.moderator)
        response = self.client.get(reverse("dashboard-announcements"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Moderator cannot create
        response = self.client.post(
            reverse("dashboard-announcements"),
            {"title": "Test2", "body": "Body2", "level": "info"},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------
    # Role Management
    # -------------------------------------------------------------------

    def test_role_management_list_and_promote(self):
        self.authenticate(self.admin)
        url = reverse("dashboard-roles")

        # List all users
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["data"]), 3)

        # Filter by role
        response = self.client.get(url, {"role": "student"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for u in response.data["data"]:
            self.assertEqual(u["role"], "student")

        # Promote user to moderator
        response = self.client.post(url, {"user_id": self.user.id, "role": "moderator"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["new_role"], "moderator")

        # Verify promotion persisted
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.role, "moderator")

    def test_role_management_moderator_denied(self):
        self.authenticate(self.moderator)
        url = reverse("dashboard-roles")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------
    # Platform Settings
    # -------------------------------------------------------------------

    def test_platform_settings_crud(self):
        self.authenticate(self.admin)
        url = reverse("dashboard-settings")

        # Get (empty initially)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Create a setting
        response = self.client.patch(url, {
            "key": "max_community_members",
            "value": 500,
            "description": "Maximum number of members per community",
        }, format="json")
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])
        self.assertEqual(response.data["data"]["key"], "max_community_members")

        # Update the same setting
        response = self.client.patch(url, {
            "key": "max_community_members",
            "value": 1000,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["value"], 1000)

        # Verify stored
        self.assertEqual(PlatformSetting.objects.count(), 1)
        setting = PlatformSetting.objects.get(key="max_community_members")
        self.assertEqual(setting.value, 1000)

    def test_platform_settings_moderator_denied(self):
        self.authenticate(self.moderator)
        url = reverse("dashboard-settings")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
