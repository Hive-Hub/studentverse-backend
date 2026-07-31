from __future__ import annotations

import logging
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from apps.messaging.models import Message
from apps.moderation.models import MessageAuditLog

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Message)
def track_message_old_content(sender, instance, **kwargs):
    if instance.id:
        try:
            old_instance = Message.objects.get(pk=instance.id)
            if old_instance.content != instance.content:
                instance._old_content = old_instance.content
        except Message.DoesNotExist:
            pass


@receiver(post_save, sender=Message)
def log_message_save(sender, instance, created, **kwargs):
    if created:
        MessageAuditLog.objects.create(
            message_id=instance.id,
            channel_id=instance.channel_id,
            author=instance.author,
            action="created",
            new_content=instance.content,
        )
    else:
        # Check if content changed
        old_content = getattr(instance, "_old_content", None)
        if old_content is not None:
            MessageAuditLog.objects.create(
                message_id=instance.id,
                channel_id=instance.channel_id,
                author=instance.author,
                action="edited",
                old_content=old_content,
                new_content=instance.content,
            )


@receiver(post_delete, sender=Message)
def log_message_delete(sender, instance, **kwargs):
    MessageAuditLog.objects.create(
        message_id=instance.id,
        channel_id=instance.channel_id,
        author=instance.author,
        action="deleted",
        old_content=instance.content,
    )
