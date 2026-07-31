from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.health.views import HealthCheckView
from apps.accounts.views import UserProfileViewSet, StorageViewSet

router = DefaultRouter()
router.register(r"profiles", UserProfileViewSet, basename="profiles")
router.register(r"storage", StorageViewSet, basename="storage")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.health.urls")),
    path("api/v1/", include("apps.communities.urls")),
    path("api/v1/", include("apps.news.urls")),
    path("api/v1/", include("apps.events.urls")),
    path("api/v1/", include("apps.notifications.urls")),
    path("api/v1/", include("apps.search.urls")),
    path("api/v1/", include("apps.messaging.urls")),
    path("api/v1/moderation/", include("apps.moderation.urls")),
    path("api/v1/dashboard/", include("apps.dashboard.urls")),
    path("api/v1/public/", include("apps.public.urls")),
    path("api/v1/", include(router.urls)),
]

