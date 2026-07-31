from __future__ import annotations

import re
import uuid
from typing import Any

from django.contrib.auth import get_user_model

from .models import UserProfile



def normalize_role(role_value: Any) -> str:
    if role_value is None:
        return UserProfile.Role.STUDENT
    normalized_value = str(role_value).strip().lower()
    allowed_roles = {choice_value for choice_value, _ in UserProfile.Role.choices}
    if normalized_value not in allowed_roles:
        raise ValueError("Invalid role value.")
    return normalized_value


def generate_unique_username(base_name: str) -> str:
    if not base_name:
        base_name = "student"
    if "@" in base_name:
        base_name = base_name.split("@")[0]

    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", base_name).strip("_")
    if not sanitized:
        sanitized = "student"

    sanitized = sanitized[:30]
    if len(sanitized) < 3:
        sanitized = f"{sanitized}_user"

    username = sanitized
    counter = 1
    while UserProfile.objects.filter(username__iexact=username).exists():
        suffix = f"_{counter}"
        max_len = 50 - len(suffix)
        username = f"{sanitized[:max_len]}{suffix}"
        counter += 1

    return username


def get_or_create_user_profile(user):
    try:
        return UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        # Determine a good base name for the handle
        base_name = user.username
        if not base_name and user.email:
            base_name = user.email.split("@")[0]
        if not base_name:
            base_name = "student"
        
        username = generate_unique_username(base_name)
        # Create user profile with a generated unique username handle
        return UserProfile.objects.create(
            user=user,
            username=username,
            full_name=user.get_full_name() or user.first_name or "",
        )


def sync_user_profile_from_firebase_claims(user, firebase_uid: str, decoded_token: dict[str, Any]):
    profile = get_or_create_user_profile(user)
    updates: list[str] = []

    if profile.firebase_uid != firebase_uid:
        profile.firebase_uid = firebase_uid
        updates.append("firebase_uid")

    display_name = decoded_token.get("name", "") or ""
    if display_name and profile.display_name != display_name:
        profile.display_name = display_name
        updates.append("display_name")

    if display_name and not profile.full_name:
        profile.full_name = display_name
        updates.append("full_name")

    token_role = decoded_token.get("role") or decoded_token.get("user_role")
    if token_role:
        normalized_role = normalize_role(token_role)
        if profile.role != normalized_role:
            profile.role = normalized_role
            updates.append("role")

    if updates:
        profile.save(update_fields=updates)

    return profile


def get_user_role(user) -> str:
    profile = get_or_create_user_profile(user)
    return profile.role


def get_user_role_display(user) -> str:
    profile = get_or_create_user_profile(user)
    return profile.get_role_display()

