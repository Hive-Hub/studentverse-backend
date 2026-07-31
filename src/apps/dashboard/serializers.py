from __future__ import annotations

from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.dashboard.models import Announcement, PlatformSetting

User = get_user_model()


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Announcement
        fields = (
            "id",
            "title",
            "body",
            "level",
            "is_active",
            "created_by",
            "created_by_username",
            "expires_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_by", "created_by_username", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class PlatformSettingSerializer(serializers.ModelSerializer):
    updated_by_username = serializers.CharField(source="updated_by.username", read_only=True)

    class Meta:
        model = PlatformSetting
        fields = ("id", "key", "value", "description", "updated_by", "updated_by_username", "updated_at")
        read_only_fields = ("id", "updated_by", "updated_by_username", "updated_at")


class RoleUpdateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=["student", "moderator", "admin"])
