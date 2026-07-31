from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import GlobalSearchViewSet

router = DefaultRouter()
router.register(r"search", GlobalSearchViewSet, basename="search")

urlpatterns = [
    path("", include(router.urls)),
]
