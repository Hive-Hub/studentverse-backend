from __future__ import annotations

from typing import Any

from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from firebase_admin import auth as firebase_auth

from apps.common.authentication import get_firebase_app, sync_user_from_firebase_claims

from .models import UserProfile
from .services import get_or_create_user_profile
from .validators import (
    validate_firebase_id_token,
    validate_username_chars,
    validate_year,
    validate_list_of_strings,
    validate_social_url,
)


class UserProfileSerializer(serializers.ModelSerializer):
    username_system = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)

    class Meta:
        model = UserProfile
        fields = (
            "id",
            "username_system",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "firebase_uid",
            "role",
            "profile_photo",
            "full_name",
            "username",
            "bio",
            "college",
            "branch",
            "year",
            "skills",
            "interests",
            "github",
            "linkedin",
            "portfolio",
            "location",
            "achievements",
            "is_active",
            "date_joined",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "username_system",
            "email",
            "first_name",
            "last_name",
            "firebase_uid",
            "role",
            "is_active",
            "date_joined",
            "created_at",
            "updated_at",
        )

    def validate_username(self, value):
        if value:
            value = validate_username_chars(value)
            # Case-insensitive uniqueness check (excluding current instance if updating)
            qs = UserProfile.objects.filter(username__iexact=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("This username handle is already taken.")
        return value

    def validate_year(self, value):
        return validate_year(value)

    def validate_skills(self, value):
        return validate_list_of_strings(value, max_items=20, max_length=50)

    def validate_interests(self, value):
        return validate_list_of_strings(value, max_items=20, max_length=50)

    def validate_achievements(self, value):
        return validate_list_of_strings(value, max_items=10, max_length=200)

    def validate_github(self, value):
        return validate_social_url(value, "github.com")

    def validate_linkedin(self, value):
        return validate_social_url(value, "linkedin.com")

    def validate_portfolio(self, value):
        if value:
            from django.core.validators import URLValidator
            from django.core.exceptions import ValidationError
            val = URLValidator()
            try:
                val(value)
            except ValidationError:
                raise serializers.ValidationError("Enter a valid URL.")
        return value

    def validate_profile_photo(self, value):
        if value:
            max_size = 5 * 1024 * 1024
            if value.size > max_size:
                raise serializers.ValidationError("Image file size cannot exceed 5MB.")
            import os
            ext = os.path.splitext(value.name)[1].lower()
            valid_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
            if ext not in valid_extensions:
                raise serializers.ValidationError(
                    "Unsupported file extension. Allowed: " + ", ".join(valid_extensions)
                )
        return value




class CurrentUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    firebase_uid = serializers.CharField(read_only=True)

    @staticmethod
    def from_user(user):
        profile = get_or_create_user_profile(user)
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": profile.role,
            "display_name": profile.display_name,
            "firebase_uid": profile.firebase_uid,
        }


class FirebaseLoginSerializer(serializers.Serializer):
    firebase_id_token = serializers.CharField(required=False, allow_blank=False, write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        token = attrs.get("firebase_id_token") or getattr(request, "auth_token", "")
        token = validate_firebase_id_token(token)

        try:
            decoded_token = firebase_auth.verify_id_token(token, app=get_firebase_app(), clock_skew_seconds=10)
        except Exception as exc:  # pragma: no cover - external service validation
            raise serializers.ValidationError({"firebase_id_token": "Invalid Firebase ID token."}) from exc

        firebase_uid = decoded_token.get("uid") or decoded_token.get("sub")
        if not firebase_uid:
            raise serializers.ValidationError({"firebase_id_token": "Firebase token is missing the user identifier."})

        user = sync_user_from_firebase_claims(firebase_uid, decoded_token)
        profile = get_or_create_user_profile(user)

        refresh = RefreshToken.for_user(user)
        refresh["firebase_uid"] = firebase_uid
        refresh["role"] = profile.role

        attrs["user"] = user
        attrs["profile"] = profile
        attrs["decoded_token"] = decoded_token
        attrs["access"] = str(refresh.access_token)
        attrs["refresh"] = str(refresh)
        return attrs


class JWTRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

    def validate_refresh(self, value: str) -> str:
        token = value.strip()
        if not token:
            raise serializers.ValidationError("Refresh token is required.")
        return token

    def save(self, **kwargs):
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.exceptions import TokenError

        try:
            token = RefreshToken(self.validated_data["refresh"])
            token.blacklist()
        except TokenError as exc:
            raise serializers.ValidationError({"refresh": "Invalid or expired refresh token."}) from exc
        return token


class ProfileUpdateSerializer(UserProfileSerializer):
    pass

