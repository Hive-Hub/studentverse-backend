from __future__ import annotations

from django.urls import path
from .views import (
    PlatformStatsView,
    TrendingCommunitiesView,
    FeaturedNewsView,
    UpcomingEventsView,
    CommunityStatsView,
    PublicProfileView,
    SeoCommunitView,
    SeoNewsView,
    SeoEventView,
    OgCommunityView,
    OgNewsView,
)

urlpatterns = [
    path("stats/", PlatformStatsView.as_view(), name="public-platform-stats"),
    path("trending/communities/", TrendingCommunitiesView.as_view(), name="public-trending-communities"),
    path("featured/news/", FeaturedNewsView.as_view(), name="public-featured-news"),
    path("upcoming/events/", UpcomingEventsView.as_view(), name="public-upcoming-events"),
    path("communities/<slug:slug>/stats/", CommunityStatsView.as_view(), name="public-community-stats"),
    path("profiles/<str:username>/", PublicProfileView.as_view(), name="public-profile"),
    path("seo/community/<slug:slug>/", SeoCommunitView.as_view(), name="public-seo-community"),
    path("seo/news/<int:news_id>/", SeoNewsView.as_view(), name="public-seo-news"),
    path("seo/event/<int:pk>/", SeoEventView.as_view(), name="public-seo-event"),
    path("og/community/<slug:slug>/", OgCommunityView.as_view(), name="public-og-community"),
    path("og/news/<int:news_id>/", OgNewsView.as_view(), name="public-og-news"),
]
