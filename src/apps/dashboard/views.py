from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Count, Q, Sum, Avg
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.responses import error_response, success_response
from apps.communities.models import Community, CommunityMember, Channel
from apps.dashboard.models import Announcement, PlatformSetting
from apps.dashboard.serializers import (
    AnnouncementSerializer,
    PlatformSettingSerializer,
    RoleUpdateSerializer,
)
from apps.events.models import Event
from apps.logs.models import LogEntry
from apps.messaging.models import Message
from apps.moderation.models import CommunityBan, MessageAuditLog, Report, UserMute
from apps.news.models import News
from apps.notifications.models import Notification

User = get_user_model()
logger = logging.getLogger(__name__)


def _require_admin(user) -> bool:
    return (
        not user.is_anonymous
        and getattr(user, "profile", None) is not None
        and user.profile.role == "admin"
    )


def _require_mod_or_admin(user) -> bool:
    return (
        not user.is_anonymous
        and getattr(user, "profile", None) is not None
        and user.profile.role in ("admin", "moderator")
    )


# ---------------------------------------------------------------------------
# 1. Overview Statistics
# ---------------------------------------------------------------------------

class OverviewStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _require_mod_or_admin(request.user):
            return error_response(message="Access denied.", status_code=status.HTTP_403_FORBIDDEN)

        now = timezone.now()
        active_mutes = UserMute.objects.filter(
            Q(expires_at__gt=now) | Q(expires_at__isnull=True)
        ).count()

        data = {
            "users": User.objects.count(),
            "communities": Community.objects.count(),
            "channels": Channel.objects.count(),
            "messages": Message.objects.count(),
            "news": News.objects.count(),
            "events": Event.objects.count(),
            "notifications": Notification.objects.count(),
            "pending_reports": Report.objects.filter(status="pending").count(),
            "active_bans": CommunityBan.objects.count(),
            "active_mutes": active_mutes,
        }
        return success_response(data=data, message="Overview stats retrieved.")


# ---------------------------------------------------------------------------
# 2. User Statistics
# ---------------------------------------------------------------------------

class UserStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _require_admin(request.user):
            return error_response(message="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)

        days = int(request.query_params.get("days", 30))
        since = timezone.now() - timedelta(days=days)

        # Daily user growth
        daily_growth = (
            User.objects.filter(date_joined__gte=since)
            .extra(select={"day": "DATE(date_joined)"})
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )

        # Role breakdown
        role_breakdown = (
            User.objects.values("profile__role")
            .annotate(count=Count("id"))
            .order_by("profile__role")
        )

        # Top users by activity (messages + news articles)
        top_users = (
            User.objects.annotate(
                message_count=Count("sent_messages", distinct=True),
                news_count=Count("news_articles", distinct=True),
            )
            .order_by("-message_count")[:10]
            .values("id", "username", "email", "message_count", "news_count")
        )

        data = {
            "total_users": User.objects.count(),
            "new_users_in_period": User.objects.filter(date_joined__gte=since).count(),
            "daily_growth": list(daily_growth),
            "role_breakdown": list(role_breakdown),
            "top_active_users": list(top_users),
        }
        return success_response(data=data, message="User stats retrieved.")


# ---------------------------------------------------------------------------
# 3. Content Statistics
# ---------------------------------------------------------------------------

class ContentStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _require_mod_or_admin(request.user):
            return error_response(message="Access denied.", status_code=status.HTTP_403_FORBIDDEN)

        days = int(request.query_params.get("days", 30))
        since = timezone.now() - timedelta(days=days)

        data = {
            "total_messages": Message.objects.count(),
            "messages_in_period": Message.objects.filter(created_at__gte=since).count(),
            "total_news": News.objects.count(),
            "news_in_period": News.objects.filter(created_at__gte=since).count(),
            "total_events": Event.objects.count(),
            "events_in_period": Event.objects.filter(created_at__gte=since).count(),
            "total_communities": Community.objects.count(),
            "total_channels": Channel.objects.count(),
            "total_notifications": Notification.objects.count(),
        }
        return success_response(data=data, message="Content stats retrieved.")


# ---------------------------------------------------------------------------
# 4. Storage Analytics
# ---------------------------------------------------------------------------

class StorageStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _require_admin(request.user):
            return error_response(message="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)

        try:
            from apps.accounts.models import UserStorageUsage
            agg = UserStorageUsage.objects.aggregate(total=Sum("bytes_used"))
            total_bytes = agg["total"] or 0

            top_uploaders = (
                UserStorageUsage.objects.select_related("user")
                .order_by("-bytes_used")[:10]
                .values("user__username", "bytes_used")
            )

            data = {
                "total_bytes_used": total_bytes,
                "total_mb_used": round(total_bytes / (1024 * 1024), 2),
                "top_uploaders": list(top_uploaders),
            }
        except Exception as e:
            data = {"total_bytes_used": 0, "total_mb_used": 0.0, "top_uploaders": [], "note": str(e)}

        return success_response(data=data, message="Storage analytics retrieved.")


# ---------------------------------------------------------------------------
# 5. Moderation Queue
# ---------------------------------------------------------------------------

class ModerationQueueView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _require_mod_or_admin(request.user):
            return error_response(message="Access denied.", status_code=status.HTTP_403_FORBIDDEN)

        pending = Report.objects.filter(status="pending").select_related("reporter").order_by("-created_at")

        # Optional filters
        report_type = request.query_params.get("report_type")
        if report_type:
            pending = pending.filter(report_type=report_type)

        page_size = min(int(request.query_params.get("page_size", 20)), 100)
        offset = int(request.query_params.get("offset", 0))
        total = pending.count()
        items = pending[offset: offset + page_size]

        data = [
            {
                "id": r.id,
                "report_type": r.report_type,
                "target_id": r.target_id,
                "reason": r.reason,
                "details": r.details,
                "reporter": {"id": r.reporter.id, "username": r.reporter.username} if r.reporter else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in items
        ]
        return success_response(
            data=data,
            message="Moderation queue retrieved.",
            meta={"total": total, "offset": offset, "page_size": page_size},
        )


# ---------------------------------------------------------------------------
# 6. System Health
# ---------------------------------------------------------------------------

class SystemHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _require_admin(request.user):
            return error_response(message="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)

        health: dict = {}

        # Database
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health["database"] = {"status": "ok"}
        except Exception as e:
            health["database"] = {"status": "error", "detail": str(e)}

        # Redis / Channel Layer
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.send)(
                    "health-check", {"type": "health.ping"}
                )
            health["redis"] = {"status": "ok"}
        except Exception as e:
            health["redis"] = {"status": "error", "detail": str(e)}

        # Overall
        all_ok = all(v.get("status") == "ok" for v in health.values())
        health["overall"] = "healthy" if all_ok else "degraded"

        return success_response(data=health, message="System health retrieved.")


# ---------------------------------------------------------------------------
# 7. API Usage
# ---------------------------------------------------------------------------

class ApiUsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _require_admin(request.user):
            return error_response(message="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)

        hours = int(request.query_params.get("hours", 24))
        since = timezone.now() - timedelta(hours=hours)

        usage = (
            LogEntry.objects.filter(
                logger_name="apps.logs.request",
                created_at__gte=since,
            )
            .values("request_method", "request_path", "status_code")
            .annotate(
                count=Count("id"),
                avg_duration_ms=Avg("duration_ms"),
            )
            .order_by("-count")[:50]
        )

        total_requests = LogEntry.objects.filter(
            logger_name="apps.logs.request",
            created_at__gte=since,
        ).count()

        data = {
            "period_hours": hours,
            "total_requests": total_requests,
            "top_endpoints": list(usage),
        }
        return success_response(data=data, message="API usage retrieved.")


# ---------------------------------------------------------------------------
# 8. Audit Logs (LogEntry Feed)
# ---------------------------------------------------------------------------

class AuditLogsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _require_mod_or_admin(request.user):
            return error_response(message="Access denied.", status_code=status.HTTP_403_FORBIDDEN)

        qs = LogEntry.objects.all()

        level = request.query_params.get("level")
        path = request.query_params.get("path")
        hours = request.query_params.get("hours")

        if level:
            qs = qs.filter(level=level.upper())
        if path:
            qs = qs.filter(request_path__icontains=path)
        if hours:
            since = timezone.now() - timedelta(hours=int(hours))
            qs = qs.filter(created_at__gte=since)

        page_size = min(int(request.query_params.get("page_size", 50)), 200)
        offset = int(request.query_params.get("offset", 0))
        total = qs.count()
        items = qs[offset: offset + page_size]

        data = [
            {
                "id": e.id,
                "level": e.level,
                "logger_name": e.logger_name,
                "message": e.message[:200],
                "request_method": e.request_method,
                "request_path": e.request_path,
                "status_code": e.status_code,
                "duration_ms": float(e.duration_ms) if e.duration_ms else None,
                "remote_addr": e.remote_addr,
                "created_at": e.created_at.isoformat(),
            }
            for e in items
        ]
        return success_response(
            data=data,
            message="Audit logs retrieved.",
            meta={"total": total, "offset": offset, "page_size": page_size},
        )


# ---------------------------------------------------------------------------
# 9 & 10. Announcements CRUD
# ---------------------------------------------------------------------------

class AnnouncementListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _require_mod_or_admin(request.user):
            return error_response(message="Access denied.", status_code=status.HTTP_403_FORBIDDEN)

        active_only = request.query_params.get("active_only", "false").lower() in ("true", "1")
        qs = Announcement.objects.all()
        if active_only:
            now = timezone.now()
            qs = qs.filter(is_active=True).filter(
                Q(expires_at__gt=now) | Q(expires_at__isnull=True)
            )
        serializer = AnnouncementSerializer(qs, many=True)
        return success_response(data=serializer.data, message="Announcements retrieved.")

    def post(self, request):
        if not _require_admin(request.user):
            return error_response(message="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)

        serializer = AnnouncementSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(data=serializer.data, message="Announcement created.", status_code=status.HTTP_201_CREATED)


class AnnouncementDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_object(self, pk):
        try:
            return Announcement.objects.get(pk=pk)
        except Announcement.DoesNotExist:
            return None

    def get(self, request, pk):
        if not _require_mod_or_admin(request.user):
            return error_response(message="Access denied.", status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get_object(pk)
        if not obj:
            return error_response(message="Announcement not found.", status_code=status.HTTP_404_NOT_FOUND)
        return success_response(data=AnnouncementSerializer(obj).data, message="Announcement retrieved.")

    def patch(self, request, pk):
        if not _require_admin(request.user):
            return error_response(message="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get_object(pk)
        if not obj:
            return error_response(message="Announcement not found.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = AnnouncementSerializer(obj, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(data=serializer.data, message="Announcement updated.")

    def delete(self, request, pk):
        if not _require_admin(request.user):
            return error_response(message="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get_object(pk)
        if not obj:
            return error_response(message="Announcement not found.", status_code=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return success_response(message="Announcement deleted.")


# ---------------------------------------------------------------------------
# 11. Role Management
# ---------------------------------------------------------------------------

class RoleManagementView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _require_admin(request.user):
            return error_response(message="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)

        role_filter = request.query_params.get("role")
        search = request.query_params.get("search")
        qs = User.objects.select_related("profile").all()

        if role_filter:
            qs = qs.filter(profile__role=role_filter)
        if search:
            qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search))

        page_size = min(int(request.query_params.get("page_size", 50)), 200)
        offset = int(request.query_params.get("offset", 0))
        total = qs.count()
        items = qs[offset: offset + page_size]

        data = [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.profile.role if hasattr(u, "profile") else "student",
                "date_joined": u.date_joined.isoformat(),
            }
            for u in items
        ]
        return success_response(
            data=data,
            message="Users retrieved.",
            meta={"total": total, "offset": offset, "page_size": page_size},
        )

    def post(self, request):
        """Promote or demote a user's platform role."""
        if not _require_admin(request.user):
            return error_response(message="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)

        serializer = RoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            target = User.objects.select_related("profile").get(pk=serializer.validated_data["user_id"])
        except User.DoesNotExist:
            return error_response(message="User not found.", status_code=status.HTTP_404_NOT_FOUND)

        target.profile.role = serializer.validated_data["role"]
        target.profile.save(update_fields=["role"])
        return success_response(
            data={"id": target.id, "username": target.username, "new_role": target.profile.role},
            message=f"Role updated to '{target.profile.role}' for {target.username}.",
        )


# ---------------------------------------------------------------------------
# 12. Platform Settings
# ---------------------------------------------------------------------------

class PlatformSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _require_admin(request.user):
            return error_response(message="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)

        qs = PlatformSetting.objects.all()
        serializer = PlatformSettingSerializer(qs, many=True)
        return success_response(data=serializer.data, message="Platform settings retrieved.")

    def patch(self, request):
        if not _require_admin(request.user):
            return error_response(message="Admin access required.", status_code=status.HTTP_403_FORBIDDEN)

        key = request.data.get("key")
        value = request.data.get("value")
        description = request.data.get("description", "")

        if not key:
            return error_response(message="'key' is required.", status_code=status.HTTP_400_BAD_REQUEST)

        setting, created = PlatformSetting.objects.update_or_create(
            key=key,
            defaults={"value": value, "description": description, "updated_by": request.user},
        )
        serializer = PlatformSettingSerializer(setting)
        return success_response(
            data=serializer.data,
            message=f"Setting '{key}' {'created' if created else 'updated'}.",
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
