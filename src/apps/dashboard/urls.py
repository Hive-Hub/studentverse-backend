from __future__ import annotations

from django.urls import path
from .views import (
    OverviewStatsView,
    UserStatsView,
    ContentStatsView,
    StorageStatsView,
    ModerationQueueView,
    SystemHealthView,
    ApiUsageView,
    AuditLogsView,
    AnnouncementListCreateView,
    AnnouncementDetailView,
    RoleManagementView,
    PlatformSettingsView,
)

urlpatterns = [
    path("stats/overview/", OverviewStatsView.as_view(), name="dashboard-overview"),
    path("stats/users/", UserStatsView.as_view(), name="dashboard-user-stats"),
    path("stats/content/", ContentStatsView.as_view(), name="dashboard-content-stats"),
    path("stats/storage/", StorageStatsView.as_view(), name="dashboard-storage-stats"),
    path("moderation/queue/", ModerationQueueView.as_view(), name="dashboard-moderation-queue"),
    path("health/", SystemHealthView.as_view(), name="dashboard-health"),
    path("api-usage/", ApiUsageView.as_view(), name="dashboard-api-usage"),
    path("audit-logs/", AuditLogsView.as_view(), name="dashboard-audit-logs"),
    path("announcements/", AnnouncementListCreateView.as_view(), name="dashboard-announcements"),
    path("announcements/<int:pk>/", AnnouncementDetailView.as_view(), name="dashboard-announcement-detail"),
    path("roles/", RoleManagementView.as_view(), name="dashboard-roles"),
    path("settings/", PlatformSettingsView.as_view(), name="dashboard-settings"),
]
