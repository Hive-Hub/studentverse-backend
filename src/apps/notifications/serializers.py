from __future__ import annotations

from rest_framework import serializers
from .models import Notification, PushDevice, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = (
            "id",
            "recipient",
            "notification_type",
            "title",
            "content",
            "is_read",
            "data",
            "created_at",
            "read_at",
        )
        read_only_fields = ("recipient", "is_read", "created_at", "read_at")


class PushDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushDevice
        fields = ("id", "registration_token", "device_type", "created_at", "updated_at")
        read_only_fields = ("created_at", "updated_at")


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ("muted_communities", "muted_channels", "muted_events", "muted_types")
