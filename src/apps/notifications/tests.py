from __future__ import annotations

import json
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITransactionTestCase

from apps.notifications.models import Notification, PushDevice, NotificationPreference
from apps.notifications.services import create_notification
from apps.notifications.websocket import user_websocket_connections

User = get_user_model()


class NotificationAPITests(APITransactionTestCase):
    def setUp(self):
        # Mock FCM send
        self.fcm_patcher = patch("firebase_admin.messaging.send")
        self.mock_fcm_send = self.fcm_patcher.start()
        self.mock_fcm_send.return_value = "mock_message_id"

        # Create test users
        self.user1 = User.objects.create_user(username="user1", email="user1@example.com", password="Password123")
        self.user2 = User.objects.create_user(username="user2", email="user2@example.com", password="Password123")

    def tearDown(self):
        self.fcm_patcher.stop()

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    # --- CRUD Actions ---

    def test_notification_list_and_unread_count(self):
        self.authenticate(self.user1)
        
        # Create some notifications
        Notification.objects.create(recipient=self.user1, notification_type="system", title="Welcome", content="Hi!")
        Notification.objects.create(recipient=self.user1, notification_type="mention", title="Alert", content="Yo!", is_read=True)

        url = reverse("notifications-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 2)

        # Filter unread
        response = self.client.get(url, {"is_read": "false"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)

        # Unread count endpoint
        count_url = reverse("notifications-unread-count")
        response = self.client.get(count_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["unread_count"], 1)

    # --- Read/Write Marks & Deletion ---

    def test_mark_read_and_delete(self):
        self.authenticate(self.user1)
        notif = Notification.objects.create(recipient=self.user1, notification_type="reply", title="Reply", content="Yes")
        
        # Mark Read
        read_url = reverse("notifications-mark-read", kwargs={"pk": notif.id})
        response = self.client.post(read_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Notification.objects.get(id=notif.id).is_read)

        # Delete
        delete_url = reverse("notifications-detail", kwargs={"pk": notif.id})
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Notification.objects.filter(id=notif.id).exists())

    def test_batch_operations(self):
        self.authenticate(self.user1)
        n1 = Notification.objects.create(recipient=self.user1, notification_type="reply", title="1", content="a")
        n2 = Notification.objects.create(recipient=self.user1, notification_type="reply", title="2", content="b")
        n3 = Notification.objects.create(recipient=self.user1, notification_type="reply", title="3", content="c")

        # Batch Mark Read
        batch_read_url = reverse("notifications-batch-mark-read")
        response = self.client.post(batch_read_url, {"ids": [n1.id, n2.id]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Notification.objects.get(id=n1.id).is_read)
        self.assertTrue(Notification.objects.get(id=n2.id).is_read)
        self.assertFalse(Notification.objects.get(id=n3.id).is_read)

        # Batch Delete
        batch_delete_url = reverse("notifications-batch-delete")
        response = self.client.post(batch_delete_url, {"ids": [n1.id, n3.id]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Notification.objects.filter(id=n1.id).exists())
        self.assertFalse(Notification.objects.filter(id=n3.id).exists())
        self.assertTrue(Notification.objects.filter(id=n2.id).exists())

    # --- Preference Muting ---

    def test_notification_preferences_muting(self):
        # Retrieve preferences
        self.authenticate(self.user1)
        prefs_url = reverse("notifications-preferences")
        response = self.client.get(prefs_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Update preferences: mute news type and community ID 99
        data = {
            "muted_types": ["news"],
            "muted_communities": [99]
        }
        response = self.client.patch(prefs_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("news", response.data["data"]["muted_types"])
        self.assertIn(99, response.data["data"]["muted_communities"])

        # Test creation suppression
        # 1. Type "news" is muted -> should return None and not create db row
        n_news = create_notification(self.user1, "news", "New News", "Read me")
        self.assertIsNone(n_news)

        # 2. Community 99 is muted -> should return None and not create db row
        n_comm_muted = create_notification(self.user1, "event", "Comm Event", "Join", {"community_id": 99})
        self.assertIsNone(n_comm_muted)

        # 3. Community 88 is NOT muted -> should create notification successfully
        n_comm_allowed = create_notification(self.user1, "event", "Comm Event 2", "Join", {"community_id": 88})
        self.assertIsNotNone(n_comm_allowed)
        self.assertEqual(n_comm_allowed.title, "Comm Event 2")

    # --- Push Tokens ---

    def test_push_token_registration(self):
        self.authenticate(self.user1)
        url = reverse("push-devices-list")

        # Register device token
        data = {
            "registration_token": "fcm_token_xyz_123",
            "device_type": "android"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(PushDevice.objects.filter(user=self.user1, registration_token="fcm_token_xyz_123").exists())

    # --- Live WebSocket Client Handshake ---

    @patch("apps.notifications.websocket.send_live_notification")
    def test_websocket_application_handshake(self, mock_ws_send):
        from config.asgi import websocket_application
        from rest_framework_simplejwt.tokens import AccessToken
        
        # Generate token
        token = str(AccessToken.for_user(self.user1))

        # Helper to simulate ASGI loop
        async def mock_receive():
            return {"type": "websocket.disconnect"}

        async def mock_send(msg):
            mock_send.messages.append(msg)
        mock_send.messages = []

        # 1. Valid token query parameter should connect successfully
        scope = {
            "type": "websocket",
            "path": "/ws/notifications/",
            "query_string": f"token={token}".encode()
        }
        
        import asyncio
        asyncio.run(websocket_application(scope, mock_receive, mock_send))
        self.assertIn({"type": "websocket.accept"}, mock_send.messages)

        # 2. Invalid token should close connection immediately
        mock_send.messages = []
        scope_invalid = {
            "type": "websocket",
            "path": "/ws/notifications/",
            "query_string": b"token=badtoken"
        }
        asyncio.run(websocket_application(scope_invalid, mock_receive, mock_send))
        self.assertIn({"type": "websocket.close"}, mock_send.messages)
