from __future__ import annotations

from django.urls import path

from .views import CurrentUserView, FirebaseLoginView, JWTRefreshView, LogoutView, ProfileView

urlpatterns = [
    path("firebase/login/", FirebaseLoginView.as_view(), name="firebase-login"),
    path("refresh/", JWTRefreshView.as_view(), name="jwt-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("profile/", ProfileView.as_view(), name="profile"),
]
