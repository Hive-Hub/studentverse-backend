from __future__ import annotations

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

django_asgi_app = get_asgi_application()

from apps.messaging.consumers import JWTAuthMiddleware, ChannelChatConsumer
from apps.news.consumers import NewsConsumer
from apps.notifications.consumers import NotificationConsumer

websocket_urlpatterns = [
    path("ws/news/", NewsConsumer.as_asgi()),
    path("ws/notifications/", NotificationConsumer.as_asgi()),
    path("ws/channels/<int:channel_id>/", ChannelChatConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})

# Backward compatibility alias for legacy handshake tests
async def websocket_application(scope, receive, send):
    path = scope.get("path", "")
    if path == "/ws/news/":
        from apps.news.websocket import register_websocket_connection, unregister_websocket_connection
        await send({"type": "websocket.accept"})
        register_websocket_connection(send)
        try:
            while True:
                message = await receive()
                if message.get("type") == "websocket.disconnect":
                    break
        finally:
            unregister_websocket_connection(send)
    elif path == "/ws/notifications/":
        from urllib.parse import parse_qs
        from rest_framework_simplejwt.tokens import AccessToken
        from django.contrib.auth import get_user_model
        
        query_string = scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token_str = params.get("token", [None])[0]
        
        user = None
        if token_str:
            try:
                access_token = AccessToken(token_str)
                user_id = access_token["user_id"]
                from channels.db import database_sync_to_async
                User = get_user_model()
                user = await database_sync_to_async(lambda uid: User.objects.get(id=uid))(user_id)
            except Exception:
                pass
                
        if not user:
            await send({"type": "websocket.close"})
            return
            
        from apps.notifications.websocket import register_notification_connection, unregister_notification_connection
        await send({"type": "websocket.accept"})
        register_notification_connection(user.id, send)
        try:
            while True:
                message = await receive()
                if message.get("type") == "websocket.disconnect":
                    break
        finally:
            unregister_notification_connection(user.id, send)
    else:
        await application(scope, receive, send)
