from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Legacy placeholders for compatibility
user_websocket_connections = {}


def register_notification_connection(user_id: int, send_func: Any) -> None:
    pass


def unregister_notification_connection(user_id: int, send_func: Any) -> None:
    pass


def send_live_notification(user_id: int, notification_data: dict[str, Any]) -> None:
    """Send a live push alert to the recipient via their active WebSocket connection."""
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            coro = channel_layer.group_send(
                f"user_notifications_{user_id}",
                {
                    "type": "new_notification",
                    "notification": notification_data
                }
            )
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(coro)
                    logger.info(f"Live notification scheduled on running event loop for user {user_id}.")
                    return
            except RuntimeError:
                pass

            from asgiref.sync import async_to_sync
            async_to_sync(lambda: coro)()
            logger.info(f"Live notification broadcasted to user {user_id} via Channels.")
        except Exception as e:
            logger.error(f"Failed to broadcast live notification: {e}")
