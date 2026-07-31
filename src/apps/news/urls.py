from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import NewsViewSet, NewsCommentViewSet, TagViewSet

router = DefaultRouter()
router.register(r"news", NewsViewSet, basename="news")
router.register(r"news/comments", NewsCommentViewSet, basename="news-comments")
router.register(r"tags", TagViewSet, basename="tags")

urlpatterns = [
    path("", include(router.urls)),
]
