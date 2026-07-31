from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)
User = get_user_model()


@database_sync_to_async
def get_user_from_scope(user_id: int) -> Any:
    try:
        return User.objects.select_related("profile").get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()


class JWTAuthMiddleware:
    """
    Middleware that authenticates WebSocket connection scope using SimpleJWT token.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        token = query_params.get("token", [None])[0]

        scope["user"] = AnonymousUser()
        if token:
            try:
                access_token = AccessToken(token)
                user_id = access_token["user_id"]
                scope["user"] = await get_user_from_scope(user_id)
            except Exception as e:
                logger.warning(f"WebSocket auth failed: {e}")

        return await self.inner(scope, receive, send)


class ChannelChatConsumer(AsyncJsonWebsocketConsumer):
    """
    Consumer handling real-time chat messages, typing indicators, reactions,
    user presence list updates, and channel broadcasts.
    """
    # Key: group_name, Value: set of user tuples (user_id, username, display_name)
    online_presences: dict[str, set[tuple[int, str, str]]] = {}

    async def connect(self):
        self.channel_id = self.scope["url_route"]["kwargs"]["channel_id"]
        self.group_name = f"channel_{self.channel_id}"
        self.user = self.scope.get("user", AnonymousUser())

        # 1. JWT Authentication
        if not self.user or self.user.is_anonymous:
            await self.close(code=4003)
            return

        # 2. Permissions check
        has_access = await self.check_channel_access(self.user, self.channel_id)
        if not has_access:
            await self.close(code=4003)
            return

        # Rate Limit parameters
        self.last_message_time = 0.0
        self.message_count_in_sec = 0

        # Join the channel group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Update online presence state
        if self.group_name not in self.online_presences:
            self.online_presences[self.group_name] = set()

        display_name = getattr(self.user.profile, "display_name", "") if hasattr(self.user, "profile") else ""
        user_info = (self.user.id, self.user.username, display_name)
        self.online_presences[self.group_name].add(user_info)

        # Broadcast updated presence list
        await self.broadcast_presence_list()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name") and hasattr(self, "user") and not self.user.is_anonymous:
            # Leave channel group
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

            # Update presence state
            if self.group_name in self.online_presences:
                display_name = getattr(self.user.profile, "display_name", "") if hasattr(self.user, "profile") else ""
                user_info = (self.user.id, self.user.username, display_name)
                self.online_presences[self.group_name].discard(user_info)
                if not self.online_presences[self.group_name]:
                    del self.online_presences[self.group_name]

            # Broadcast updated presence list
            await self.broadcast_presence_list()

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type")

        # 1. Heartbeat check
        if msg_type == "ping":
            await self.send_json({"type": "pong"})
            return

        # 2. Throttling / Rate Limiting (max 5 requests per second)
        current_time = time.time()
        if current_time - self.last_message_time < 1.0:
            self.message_count_in_sec += 1
            if self.message_count_in_sec > 5:
                await self.send_json({
                    "type": "error",
                    "message": "Rate limit exceeded. Maximum 5 messages per second."
                })
                return
        else:
            self.last_message_time = current_time
            self.message_count_in_sec = 1

        # 3. Typing indicator
        if msg_type == "typing":
            is_typing = content.get("is_typing", False)
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "typing_indicator",
                    "user_id": self.user.id,
                    "username": self.user.username,
                    "is_typing": is_typing
                }
            )

    async def broadcast_presence_list(self):
        users_list = []
        if self.group_name in self.online_presences:
            for uid, uname, dname in self.online_presences[self.group_name]:
                users_list.append({
                    "id": uid,
                    "username": uname,
                    "display_name": dname
                })

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "presence_update",
                "online_users": users_list
            }
        )

    # Event handlers matching group_send events
    async def presence_update(self, event):
        await self.send_json({
            "type": "presence_update",
            "online_users": event["online_users"]
        })

    async def typing_indicator(self, event):
        # Do not broadcast back to sender
        if event["user_id"] != self.user.id:
            await self.send_json({
                "type": "typing",
                "user_id": event["user_id"],
                "username": event["username"],
                "is_typing": event["is_typing"]
            })

    async def chat_message(self, event):
        await self.send_json({
            "type": "message",
            "message": event["message"]
        })

    async def message_edited(self, event):
        await self.send_json({
            "type": "message_edited",
            "message": event["message"]
        })

    async def message_deleted(self, event):
        await self.send_json({
            "type": "message_deleted",
            "message_id": event["message_id"]
        })

    async def reaction_broadcast(self, event):
        await self.send_json({
            "type": "reaction",
            "message_id": event["message_id"],
            "reactions": event["reactions"]
        })

    async def pinned_broadcast(self, event):
        await self.send_json({
            "type": "pinned_broadcast",
            "message_id": event["message_id"],
            "is_pinned": event["is_pinned"]
        })

    @database_sync_to_async
    def check_channel_access(self, user, channel_id) -> bool:
        from apps.communities.models import Channel
        try:
            channel = Channel.objects.select_related("community").get(id=channel_id)
            community = channel.community
            if community.is_public:
                return True
            return community.memberships.filter(user=user).exists()
        except Channel.DoesNotExist:
            return False
