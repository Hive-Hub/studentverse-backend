from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import EventViewSet, EventCommentViewSet

router = DefaultRouter()
router.register(r"events", EventViewSet, basename="events")
router.register(r"events/comments", EventCommentViewSet, basename="events-comments")

urlpatterns = [
    path("", include(router.urls)),
]
