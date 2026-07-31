from __future__ import annotations

import threading
from typing import Any
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model


class CurrentUserMiddleware:
    """Middleware that stores the current request user in thread-local storage."""
    _thread_locals = threading.local()

    @classmethod
    def get_current_user(cls) -> Any | None:
        return getattr(cls._thread_locals, "user", None)

    @classmethod
    def set_current_user(cls, user: Any) -> None:
        cls._thread_locals.user = user

    @classmethod
    def clear_current_user(cls) -> None:
        if hasattr(cls._thread_locals, "user"):
            del cls._thread_locals.user

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self.set_current_user(request.user if hasattr(request, "user") else None)
        try:
            return self.get_response(request)
        finally:
            self.clear_current_user()


class AuthTokenContextMiddleware:
    """
    Middleware that authenticates the user using JWT or Firebase token 
    from the Authorization header early in the middleware cycle.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = AnonymousUser()
        request.auth_token = ""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            request.auth_token = token
            try:
                # Attempt standard JWT authentication decoding
                from rest_framework_simplejwt.tokens import AccessToken
                User = get_user_model()
                access_token = AccessToken(token)
                user_id = access_token["user_id"]
                request.user = User.objects.get(id=user_id)
            except Exception:
                try:
                    # Fallback to Firebase authentication decoding
                    from firebase_admin import auth as firebase_auth
                    decoded_token = firebase_auth.verify_id_token(token)
                    uid = decoded_token.get("uid")
                    User = get_user_model()
                    request.user = User.objects.get(username=uid)
                except Exception:
                    pass

        return self.get_response(request)
