from __future__ import annotations

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ReportViewSet,
    BlockedWordViewSet,
    MuteUserView,
    UnmuteUserView,
    KickUserView,
    BanUserView,
    UnbanUserView,
    AdminDashboardStatsView,
    MessageAuditLogListView,
)

router = DefaultRouter()
router.register(r"reports", ReportViewSet, basename="report")
router.register(r"blocked-words", BlockedWordViewSet, basename="blocked-word")

urlpatterns = [
    path("", include(router.urls)),
    path("mute/", MuteUserView.as_view(), name="moderation-mute"),
    path("unmute/", UnmuteUserView.as_view(), name="moderation-unmute"),
    path("kick/", KickUserView.as_view(), name="moderation-kick"),
    path("ban/", BanUserView.as_view(), name="moderation-ban"),
    path("unban/", UnbanUserView.as_view(), name="moderation-unban"),
    path("dashboard/stats/", AdminDashboardStatsView.as_view(), name="moderation-dashboard-stats"),
    path("audit-logs/", MessageAuditLogListView.as_view(), name="moderation-audit-logs"),
]
