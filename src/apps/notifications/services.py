from __future__ import annotations

from typing import Any
from apps.notifications.models import Notification, NotificationPreference, PushDevice
from apps.notifications.fcm import send_fcm_notification
from apps.notifications.websocket import send_live_notification


def create_notification(
    recipient: Any,
    notification_type: str,
    title: str,
    content: str,
    data: dict[str, Any] | None = None
) -> Notification | None:
    """Central service to create notifications, check mute preferences, and broadcast live alerts."""
    pref, _ = NotificationPreference.objects.get_or_create(user=recipient)

    # Check notification type preference
    if notification_type in pref.muted_types:
        return None

    # Check muted entities in payload
    if data:
        community_id = data.get("community_id")
        if community_id and community_id in pref.muted_communities:
            return None
            
        channel_id = data.get("channel_id")
        if channel_id and channel_id in pref.muted_channels:
            return None
            
        event_id = data.get("event_id")
        if event_id and event_id in pref.muted_events:
            return None

    # Create Notification record
    notification = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        content=content,
        data=data or {}
    )

    # Serialize and broadcast via WebSockets
    from apps.notifications.serializers import NotificationSerializer
    serialized = NotificationSerializer(notification).data
    send_live_notification(recipient.id, serialized)

    # Push to registered devices via FCM
    devices = PushDevice.objects.filter(user=recipient)
    for device in devices:
        send_fcm_notification(device.registration_token, title, content, data)

    return notification
