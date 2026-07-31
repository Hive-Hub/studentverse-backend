from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


logger = logging.getLogger(__name__)


class FirebaseAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request):
        authorization = get_authorization_header(request).split()
        if not authorization:
            return None

        if authorization[0].lower() != self.keyword:
            return None

        if len(authorization) != 2:
            raise AuthenticationFailed("Invalid Authorization header format.")

        token = authorization[1].decode("utf-8")
        firebase_app = _get_firebase_app()

        try:
            decoded_token = firebase_auth.verify_id_token(token, app=firebase_app, clock_skew_seconds=10)
        except Exception as exc:  # pragma: no cover - external service validation
            logger.warning("Firebase token validation failed: %s", exc)
            raise AuthenticationFailed("Invalid Firebase token.") from exc

        firebase_uid = decoded_token.get("uid") or decoded_token.get("sub")
        if not firebase_uid:
            raise AuthenticationFailed("Firebase token is missing the user identifier.")

        user = _sync_user_from_firebase_claims(firebase_uid, decoded_token)
        return user, decoded_token


def _get_firebase_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        pass

    credentials_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()
    credentials_json = os.getenv("FIREBASE_CREDENTIALS_JSON", "").strip()
    project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()

    firebase_options: dict[str, Any] = {}
    if project_id:
        firebase_options["projectId"] = project_id

    if credentials_json:
        service_account_info = json.loads(credentials_json)
        firebase_credentials = credentials.Certificate(service_account_info)
    elif credentials_path:
        firebase_credentials = credentials.Certificate(str(Path(credentials_path)))
    else:
        raise AuthenticationFailed(
            "Firebase authentication is not configured. Set FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_JSON."
        )

    if firebase_options:
        return firebase_admin.initialize_app(firebase_credentials, firebase_options)
    return firebase_admin.initialize_app(firebase_credentials)


def get_firebase_app():
    return _get_firebase_app()


def verify_firebase_id_token(token: str):
    firebase_app = get_firebase_app()
    return firebase_auth.verify_id_token(token, app=firebase_app, clock_skew_seconds=10)


def _sync_user_from_firebase_claims(firebase_uid: str, decoded_token: dict[str, Any]):
    User = get_user_model()
    email = decoded_token.get("email", "")
    display_name = decoded_token.get("name", "")

    user, created = User.objects.get_or_create(
        username=firebase_uid,
        defaults={
            "email": email,
            "first_name": display_name.split(" ", 1)[0] if display_name else "",
            "last_name": display_name.split(" ", 1)[1] if display_name and " " in display_name else "",
        },
    )

    updates: list[str] = []
    if email and user.email != email:
        user.email = email
        updates.append("email")
    if display_name:
        first_name = display_name.split(" ", 1)[0]
        last_name = display_name.split(" ", 1)[1] if " " in display_name else ""
        if user.first_name != first_name:
            user.first_name = first_name
            updates.append("first_name")
        if user.last_name != last_name:
            user.last_name = last_name
            updates.append("last_name")
    if created and not user.is_active:
        user.is_active = True
        updates.append("is_active")

    if updates:
        user.save(update_fields=updates)

    try:
        from apps.accounts.services import sync_user_profile_from_firebase_claims

        sync_user_profile_from_firebase_claims(user, firebase_uid=firebase_uid, decoded_token=decoded_token)
    except Exception:  # pragma: no cover - profile sync must not block auth
        logger.exception("Failed to sync user profile from Firebase claims for %s", firebase_uid)

    return user


def sync_user_from_firebase_claims(firebase_uid: str, decoded_token: dict[str, Any]):
    return _sync_user_from_firebase_claims(firebase_uid, decoded_token)
