from __future__ import annotations

import django.utils.timezone as timezone
from django.db import models
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status, permissions, mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.responses import success_response, error_response
from .models import Notification, PushDevice, NotificationPreference
from .serializers import (
    NotificationSerializer,
    PushDeviceSerializer,
    NotificationPreferenceSerializer,
)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Notification.objects.filter(recipient=user)

        # Filters
        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            is_read_bool = is_read.lower() in ["true", "1", "yes"]
            queryset = queryset.filter(is_read=is_read_bool)

        notification_type = self.request.query_params.get("notification_type")
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)

        # Search
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(title__icontains=search) | models.Q(content__icontains=search)
            )

        return queryset

    def list(self, request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(message="Notifications retrieved.", data=serializer.data)

    def destroy(self, request, pk=None) -> Response:
        notification = get_object_or_404(Notification, id=pk, recipient=request.user)
        notification.delete()
        return success_response(message="Notification deleted successfully.")

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request) -> Response:
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return success_response(message="Unread count retrieved.", data={"unread_count": count})

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None) -> Response:
        notification = get_object_or_404(Notification, id=pk, recipient=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])
        serializer = self.get_serializer(notification)
        return success_response(message="Notification marked as read.", data=serializer.data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request) -> Response:
        Notification.objects.filter(recipient=request.user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return success_response(message="All notifications marked as read.")

    @action(detail=False, methods=["post"], url_path="batch-mark-read")
    def batch_mark_read(self, request) -> Response:
        ids = request.data.get("ids", [])
        if not isinstance(ids, list):
            return error_response(message="ids must be a list.", status_code=status.HTTP_400_BAD_REQUEST)
        
        Notification.objects.filter(recipient=request.user, id__in=ids, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return success_response(message=f"{len(ids)} notifications marked as read.")

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request) -> Response:
        ids = request.data.get("ids", [])
        if not isinstance(ids, list):
            return error_response(message="ids must be a list.", status_code=status.HTTP_400_BAD_REQUEST)

        deleted_count, _ = Notification.objects.filter(recipient=request.user, id__in=ids).delete()
        return success_response(message=f"{deleted_count} notifications deleted.")


class PushDeviceViewSet(viewsets.ModelViewSet):
    serializer_class = PushDeviceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PushDevice.objects.filter(user=self.request.user)

    def perform_create(self, serializer) -> None:
        # Use get_or_create logic to handle unique constraints cleanly
        token = serializer.validated_data.get("registration_token")
        device_type = serializer.validated_data.get("device_type")
        device, created = PushDevice.objects.get_or_create(
            registration_token=token,
            defaults={"user": self.request.user, "device_type": device_type}
        )
        if not created and device.user != self.request.user:
            device.user = self.request.user
            device.device_type = device_type
            device.save(update_fields=["user", "device_type"])

    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        device = PushDevice.objects.get(registration_token=serializer.validated_data.get("registration_token"))
        output_serializer = self.get_serializer(device)
        return success_response(
            message="Push device registered successfully.",
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED
        )

    def destroy(self, request, pk=None) -> Response:
        device = get_object_or_404(PushDevice, id=pk, user=request.user)
        device.delete()
        return success_response(message="Push device removed successfully.")


class NotificationPreferenceViewSet(viewsets.GenericViewSet):
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self) -> NotificationPreference:
        obj, _ = NotificationPreference.objects.get_or_create(user=self.request.user)
        return obj

    @action(detail=False, methods=["get", "patch", "put"])
    def preferences(self, request) -> Response:
        obj = self.get_object()
        if request.method in ["PATCH", "PUT"]:
            serializer = self.get_serializer(obj, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return success_response(message="Notification preferences updated.", data=serializer.data)
            
        serializer = self.get_serializer(obj)
        return success_response(message="Notification preferences retrieved.", data=serializer.data)
