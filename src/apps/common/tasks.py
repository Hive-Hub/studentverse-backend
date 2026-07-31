from __future__ import annotations

"""
Background Celery tasks for StudentVerse.
Each task is designed to be idempotent and safe to re-run.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------------------
# Email tasks
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_notification_email(self, user_id: int, subject: str, body: str):
    """Send a transactional notification email to a user."""
    try:
        user = User.objects.get(pk=user_id)
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info("Notification email sent to user %s (%s)", user_id, user.email)
    except User.DoesNotExist:
        logger.warning("send_notification_email: user %s not found, skipping.", user_id)
    except Exception as exc:
        logger.error("send_notification_email failed for user %s: %s", user_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_bulk_announcement_email(self, user_ids: list[int], subject: str, body: str):
    """Send announcement email to a batch of users."""
    recipients = list(
        User.objects.filter(pk__in=user_ids, is_active=True).values_list("email", flat=True)
    )
    if not recipients:
        return
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
        logger.info("Bulk announcement email sent to %d recipients.", len(recipients))
    except Exception as exc:
        logger.error("send_bulk_announcement_email failed: %s", exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Cleanup tasks (scheduled via Celery Beat)
# ---------------------------------------------------------------------------

@shared_task
def cleanup_expired_bans():
    """Remove expired community bans (called nightly)."""
    from apps.moderation.models import CommunityBan
    now = timezone.now()
    expired = CommunityBan.objects.filter(expires_at__lte=now)
    count = expired.count()
    expired.delete()
    logger.info("cleanup_expired_bans: removed %d expired bans.", count)
    return count


@shared_task
def cleanup_expired_mutes():
    """Remove expired user mutes (called hourly)."""
    from apps.moderation.models import UserMute
    now = timezone.now()
    expired = UserMute.objects.filter(expires_at__lte=now)
    count = expired.count()
    expired.delete()
    logger.info("cleanup_expired_mutes: removed %d expired mutes.", count)
    return count


@shared_task
def cleanup_old_logs(days: int = 90):
    """Purge log entries older than `days` (default 90 days). Called weekly."""
    from apps.logs.models import LogEntry
    cutoff = timezone.now() - timedelta(days=days)
    qs = LogEntry.objects.filter(created_at__lte=cutoff)
    count = qs.count()
    qs.delete()
    logger.info("cleanup_old_logs: deleted %d log entries older than %d days.", count, days)
    return count


@shared_task
def prune_expired_announcements():
    """Deactivate announcements whose expires_at has passed (called hourly)."""
    from apps.dashboard.models import Announcement
    now = timezone.now()
    qs = Announcement.objects.filter(is_active=True, expires_at__lte=now)
    count = qs.count()
    qs.update(is_active=False)
    logger.info("prune_expired_announcements: deactivated %d announcements.", count)
    return count


@shared_task
def generate_weekly_stats_snapshot():
    """
    Persist a platform stats snapshot as a PlatformSetting entry.
    Called every Monday at 00:00 UTC.
    """
    from django.contrib.auth import get_user_model
    from apps.communities.models import Community
    from apps.news.models import News
    from apps.events.models import Event
    from apps.messaging.models import Message
    from apps.dashboard.models import PlatformSetting

    User = get_user_model()
    snapshot = {
        "captured_at": timezone.now().isoformat(),
        "users": User.objects.count(),
        "communities": Community.objects.count(),
        "news": News.objects.count(),
        "events": Event.objects.count(),
        "messages": Message.objects.count(),
    }
    PlatformSetting.objects.update_or_create(
        key="weekly_stats_snapshot",
        defaults={"value": snapshot, "description": "Auto-generated weekly stats snapshot"},
    )
    logger.info("generate_weekly_stats_snapshot: saved snapshot %s", snapshot)
    return snapshot


@shared_task
def cleanup_orphan_search_history(days: int = 60):
    """Delete search history entries older than 60 days (called weekly)."""
    from apps.search.models import SearchHistory
    cutoff = timezone.now() - timedelta(days=days)
    qs = SearchHistory.objects.filter(searched_at__lte=cutoff)
    count = qs.count()
    qs.delete()
    logger.info("cleanup_orphan_search_history: removed %d old search entries.", count)
    return count
