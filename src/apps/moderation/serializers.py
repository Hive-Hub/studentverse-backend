from __future__ import annotations

from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.communities.serializers import UserMiniSerializer
from apps.moderation.models import Report, UserMute, CommunityBan, BlockedWord, MessageAuditLog

User = get_user_model()


class ReportSerializer(serializers.ModelSerializer):
    reporter = UserMiniSerializer(read_only=True)

    class Meta:
        model = Report
        fields = (
            "id",
            "reporter",
            "report_type",
            "target_id",
            "reason",
            "details",
            "status",
            "moderator_notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "reporter", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["reporter"] = self.context["request"].user
        return super().create(validated_data)


class UserMuteSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    community_id = serializers.IntegerField(required=False, allow_null=True)
    duration_minutes = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True)


class CommunityBanSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    community_id = serializers.IntegerField()
    ban_type = serializers.ChoiceField(choices=CommunityBan.BAN_TYPES, default="permanent")
    duration_days = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True)


class BlockedWordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlockedWord
        fields = ("id", "word", "created_at")
        read_only_fields = ("id", "created_at")


class MessageAuditLogSerializer(serializers.ModelSerializer):
    author = UserMiniSerializer(read_only=True)
    performed_by = UserMiniSerializer(read_only=True)

    class Meta:
        model = MessageAuditLog
        fields = (
            "id",
            "message_id",
            "channel_id",
            "author",
            "action",
            "old_content",
            "new_content",
            "performed_by",
            "created_at",
        )
