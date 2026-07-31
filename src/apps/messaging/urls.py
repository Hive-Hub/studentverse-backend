from __future__ import annotations

from django.urls import include, path
from apps.messaging.views import MessageViewSet, MessageAttachmentViewSet

# /api/v1/channels/<channel_id>/messages/
message_list = MessageViewSet.as_view({"get": "list", "post": "create"})
message_detail = MessageViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
message_react = MessageViewSet.as_view({"post": "react", "delete": "react"})
message_pin = MessageViewSet.as_view({"post": "pin"})
message_thread = MessageViewSet.as_view({"get": "thread"})

# /api/v1/messages/<message_id>/attachments/
attachment_list = MessageAttachmentViewSet.as_view({"post": "create"})
attachment_detail = MessageAttachmentViewSet.as_view({"delete": "destroy"})

urlpatterns = [
    # Messages nested under channel
    path(
        "channels/<int:channel_id>/messages/",
        message_list,
        name="channel-messages-list",
    ),
    path(
        "channels/<int:channel_id>/messages/<int:pk>/",
        message_detail,
        name="channel-messages-detail",
    ),
    path(
        "channels/<int:channel_id>/messages/<int:pk>/react/",
        message_react,
        name="channel-messages-react",
    ),
    path(
        "channels/<int:channel_id>/messages/<int:pk>/pin/",
        message_pin,
        name="channel-messages-pin",
    ),
    path(
        "channels/<int:channel_id>/messages/<int:pk>/thread/",
        message_thread,
        name="channel-messages-thread",
    ),
    # Attachments
    path(
        "messages/<int:message_id>/attachments/",
        attachment_list,
        name="message-attachments-list",
    ),
    path(
        "messages/<int:message_id>/attachments/<int:pk>/",
        attachment_detail,
        name="message-attachments-detail",
    ),
]
