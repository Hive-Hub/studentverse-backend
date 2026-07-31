from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from apps.communities.views import CommunityViewSet, ChannelViewSet

router = DefaultRouter()
router.register(r"communities", CommunityViewSet, basename="communities")
router.register(r"channels", ChannelViewSet, basename="channels")

urlpatterns = [
    path("", include(router.urls)),
]
