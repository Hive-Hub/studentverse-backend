from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Legacy placeholders for compatibility
active_websocket_connections = set()


def register_websocket_connection(send_func: Any) -> None:
    pass


def unregister_websocket_connection(send_func: Any) -> None:
    pass


def broadcast_news_published(news_data: dict[str, Any]) -> None:
    """Broadcast a news publication event to all connected Channels clients."""
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            coro = channel_layer.group_send(
                "news_updates",
                {
                    "type": "new_news",
                    "news": news_data
                }
            )
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(coro)
                    logger.info("News publication scheduled on running event loop.")
                    return
            except RuntimeError:
                pass

            from asgiref.sync import async_to_sync
            async_to_sync(lambda: coro)()
            logger.info("News publication broadcasted successfully via Channels.")
        except Exception as e:
            logger.error(f"Failed to broadcast news: {e}")
