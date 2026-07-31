from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, PushDeviceViewSet, NotificationPreferenceViewSet

router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="notifications")
router.register(r"push-devices", PushDeviceViewSet, basename="push-devices")

urlpatterns = [
    path("notifications/preferences/", NotificationPreferenceViewSet.as_view({
        "get": "preferences",
        "patch": "preferences",
        "put": "preferences"
    }), name="notifications-preferences"),
    path("", include(router.urls)),
]
