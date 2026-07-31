from __future__ import annotations

import asyncio
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import RefreshToken
from apps.communities.models import Community, Channel, CommunityMember
from config.asgi import application

User = get_user_model()


class WebSocketTests(TransactionTestCase):
    def setUp(self):
        # Create users
        self.user = User.objects.create_user(username="ws_user", email="ws_user@x.com")
        self.user_refresh = RefreshToken.for_user(self.user)
        self.user_token = str(self.user_refresh.access_token)

        self.outsider = User.objects.create_user(username="ws_outsider", email="ws_outsider@x.com")
        self.outsider_refresh = RefreshToken.for_user(self.outsider)
        self.outsider_token = str(self.outsider_refresh.access_token)

        # Create public community
        self.public_community = Community.objects.create(name="Public Comm", is_public=True)
        self.public_channel = Channel.objects.create(
            community=self.public_community, name="general", channel_type="general",
            permission_type=Channel.PermissionType.WRITE
        )
        CommunityMember.objects.create(
            community=self.public_community, user=self.user, role=CommunityMember.Role.MEMBER
        )

        # Create private community
        self.private_community = Community.objects.create(name="Private Comm", is_public=False)
        self.private_channel = Channel.objects.create(
            community=self.private_community, name="secret", channel_type="general",
            permission_type=Channel.PermissionType.WRITE
        )
        CommunityMember.objects.create(
            community=self.private_community, user=self.user, role=CommunityMember.Role.MEMBER
        )

    def test_websocket_auth_and_heartbeat(self):
        async def run_test():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/channels/{self.public_channel.id}/?token={self.user_token}"
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Receive initial presence list
            resp = await communicator.receive_json_from()
            self.assertEqual(resp["type"], "presence_update")
            self.assertTrue(any(u["username"] == "ws_user" for u in resp["online_users"]))

            # Send heartbeat ping
            await communicator.send_json_to({"type": "ping"})
            resp = await communicator.receive_json_from()
            self.assertEqual(resp["type"], "pong")

            await communicator.disconnect()

        asyncio.run(run_test())

    def test_anonymous_websocket_rejected(self):
        async def run_test():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/channels/{self.public_channel.id}/?token=invalid_token"
            )
            connected, _ = await communicator.connect()
            self.assertFalse(connected)

        asyncio.run(run_test())

    def test_private_channel_access_permission(self):
        async def run_test():
            # 1. User with membership connects successfully
            comm1 = WebsocketCommunicator(
                application,
                f"/ws/channels/{self.private_channel.id}/?token={self.user_token}"
            )
            connected1, _ = await comm1.connect()
            self.assertTrue(connected1)
            await comm1.disconnect()

            # 2. Outsider without membership gets rejected
            comm2 = WebsocketCommunicator(
                application,
                f"/ws/channels/{self.private_channel.id}/?token={self.outsider_token}"
            )
            connected2, _ = await comm2.connect()
            self.assertFalse(connected2)

        asyncio.run(run_test())

    def test_rate_limiting_spam_blocks(self):
        async def run_test():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/channels/{self.public_channel.id}/?token={self.user_token}"
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()  # presence_update

            # Send more than 5 requests rapidly
            for _ in range(5):
                await communicator.send_json_to({"type": "typing", "is_typing": True})

            # The 6th request should fail with error message
            await communicator.send_json_to({"type": "typing", "is_typing": True})
            response = await communicator.receive_json_from()
            self.assertEqual(response["type"], "error")
            self.assertIn("Rate limit exceeded", response["message"])

            await communicator.disconnect()

        asyncio.run(run_test())

    def test_news_subscription_broadcast(self):
        async def run_test():
            communicator = WebsocketCommunicator(application, "/ws/news/")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Trigger a publish event directly via news helper function
            from apps.news.websocket import broadcast_news_published
            broadcast_news_published({"id": 1, "title": "Realtime News"})

            # Wait for news broadcast event
            response = await communicator.receive_json_from()
            self.assertEqual(response["event"], "new_news")
            self.assertEqual(response["data"]["title"], "Realtime News")

            await communicator.disconnect()

        asyncio.run(run_test())

    def test_notification_subscription_broadcast(self):
        async def run_test():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/notifications/?token={self.user_token}"
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Trigger a live notification update
            from apps.notifications.websocket import send_live_notification
            send_live_notification(self.user.id, {"id": 101, "message": "You got a reply"})

            # Receive alert
            response = await communicator.receive_json_from()
            self.assertEqual(response["event"], "new_notification")
            self.assertEqual(response["data"]["message"], "You got a reply")

            await communicator.disconnect()

        asyncio.run(run_test())
