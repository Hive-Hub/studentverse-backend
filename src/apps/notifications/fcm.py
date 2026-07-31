from __future__ import annotations

import logging
from firebase_admin import messaging

logger = logging.getLogger(__name__)


def send_fcm_notification(registration_token: str, title: str, body: str, data: dict | None = None) -> str | None:
    """Send FCM push notification using firebase-admin SDK."""
    try:
        # Stringify key-value pairs in data payload as FCM only accepts string metadata
        data_str = {}
        if data:
            for k, v in data.items():
                data_str[k] = str(v)

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data_str,
            token=registration_token,
        )
        response = messaging.send(message)
        logger.info(f"FCM notification sent: {response}")
        return response
    except Exception as e:
        logger.warning(f"FCM push notification skipped/failed (expected in testing): {e}")
        return None
