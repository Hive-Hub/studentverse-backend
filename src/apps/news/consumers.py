from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class NewsConsumer(AsyncJsonWebsocketConsumer):
    """
    Consumer handling real-time news article publication announcements.
    """
    async def connect(self):
        self.group_name = "news_updates"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def new_news(self, event):
        await self.send_json({
            "event": "new_news",
            "data": event["news"]
        })
