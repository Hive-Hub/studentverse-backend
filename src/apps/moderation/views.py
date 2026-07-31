from __future__ import annotations

import logging
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Q
from django.contrib.auth import get_user_model
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from apps.common.responses import error_response, success_response
from apps.communities.models import Community, CommunityMember
from apps.moderation.models import Report, UserMute, CommunityBan, BlockedWord, MessageAuditLog
from apps.moderation.serializers import (
    ReportSerializer,
    UserMuteSerializer,
    CommunityBanSerializer,
    BlockedWordSerializer,
    MessageAuditLogSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


def is_platform_admin(user) -> bool:
    if not user or user.is_anonymous:
        return False
    return getattr(user, "profile", None) is not None and user.profile.role == "admin"


def is_platform_moderator(user) -> bool:
    if not user or user.is_anonymous:
        return False
    return getattr(user, "profile", None) is not None and user.profile.role in ["admin", "moderator"]


def is_community_moderator_or_higher(user, community) -> bool:
    if is_platform_moderator(user):
        return True
    return CommunityMember.objects.filter(
        community=community,
        user=user,
        role__in=[CommunityMember.Role.OWNER, CommunityMember.Role.ADMIN, CommunityMember.Role.MODERATOR],
    ).exists()


def is_community_admin_or_higher(user, community) -> bool:
    if is_platform_admin(user):
        return True
    return CommunityMember.objects.filter(
        community=community,
        user=user,
        role__in=[CommunityMember.Role.OWNER, CommunityMember.Role.ADMIN],
    ).exists()


class ReportViewSet(viewsets.ModelViewSet):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve", "partial_update", "update", "destroy"]:
            # Only platform moderators/admins can list or resolve reports
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        if not is_platform_moderator(request.user):
            return error_response(message="Access denied. Platform moderator role required.", status_code=status.HTTP_403_FORBIDDEN)
        
        status_filter = request.query_params.get("status")
        type_filter = request.query_params.get("report_type")
        qs = self.get_queryset()
        if status_filter:
            qs = qs.filter(status=status_filter)
        if type_filter:
            qs = qs.filter(report_type=type_filter)

        serializer = self.get_serializer(qs, many=True)
        return success_response(data=serializer.data, message="Reports retrieved successfully.")

    def retrieve(self, request, *args, **kwargs):
        if not is_platform_moderator(request.user):
            return error_response(message="Access denied. Platform moderator role required.", status_code=status.HTTP_403_FORBIDDEN)
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response(data=serializer.data, message="Report retrieved.")

    def partial_update(self, request, *args, **kwargs):
        if not is_platform_moderator(request.user):
            return error_response(message="Access denied. Platform moderator role required.", status_code=status.HTTP_403_FORBIDDEN)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(data=serializer.data, message="Report resolved successfully.")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(data=serializer.data, message="Report submitted successfully.", status_code=status.HTTP_201_CREATED)


class BlockedWordViewSet(viewsets.ModelViewSet):
    queryset = BlockedWord.objects.all()
    serializer_class = BlockedWordSerializer
    permission_classes = [IsAuthenticated]

    def check_permissions(self, request):
        super().check_permissions(request)
        if not is_platform_admin(request.user):
            self.permission_denied(request, message="Platform admin role required.")


class MuteUserView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UserMuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        target_user_id = serializer.validated_data["user_id"]
        community_id = serializer.validated_data.get("community_id")
        duration_minutes = serializer.validated_data.get("duration_minutes")
        reason = serializer.validated_data.get("reason", "")

        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return error_response(message="User not found.", status_code=status.HTTP_404_NOT_FOUND)

        expires_at = None
        if duration_minutes:
            expires_at = timezone.now() + timedelta(minutes=duration_minutes)

        if community_id:
            try:
                community = Community.objects.get(id=community_id)
            except Community.DoesNotExist:
                return error_response(message="Community not found.", status_code=status.HTTP_404_NOT_FOUND)

            if not is_community_moderator_or_higher(request.user, community):
                return error_response(message="Permission denied inside this community.", status_code=status.HTTP_403_FORBIDDEN)
        else:
            if not is_platform_moderator(request.user):
                return error_response(message="Platform moderator role required for platform-wide mutes.", status_code=status.HTTP_403_FORBIDDEN)
            community = None

        UserMute.objects.create(
            user=target_user,
            muted_by=request.user,
            community=community,
            reason=reason,
            expires_at=expires_at,
        )
        return success_response(message=f"User {target_user.username} muted successfully.")


class UnmuteUserView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_id = request.data.get("user_id")
        community_id = request.data.get("community_id")
        if not user_id:
            return error_response(message="user_id is required.", status_code=status.HTTP_400_BAD_REQUEST)

        if community_id:
            try:
                community = Community.objects.get(id=community_id)
            except Community.DoesNotExist:
                return error_response(message="Community not found.", status_code=status.HTTP_404_NOT_FOUND)

            if not is_community_moderator_or_higher(request.user, community):
                return error_response(message="Permission denied inside this community.", status_code=status.HTTP_403_FORBIDDEN)
            UserMute.objects.filter(user_id=user_id, community=community).delete()
        else:
            if not is_platform_moderator(request.user):
                return error_response(message="Platform moderator role required.", status_code=status.HTTP_403_FORBIDDEN)
            UserMute.objects.filter(user_id=user_id, community__isnull=True).delete()

        return success_response(message="User unmuted successfully.")


class KickUserView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_id = request.data.get("user_id")
        community_id = request.data.get("community_id")
        reason = request.data.get("reason", "")
        if not user_id or not community_id:
            return error_response(message="user_id and community_id are required.", status_code=status.HTTP_400_BAD_REQUEST)

        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return error_response(message="Community not found.", status_code=status.HTTP_404_NOT_FOUND)

        if not is_community_moderator_or_higher(request.user, community):
            return error_response(message="Permission denied inside this community.", status_code=status.HTTP_403_FORBIDDEN)

        try:
            membership = CommunityMember.objects.get(community=community, user_id=user_id)
        except CommunityMember.DoesNotExist:
            return error_response(message="Member not found in community.", status_code=status.HTTP_404_NOT_FOUND)

        # Protect Owner
        if membership.role == CommunityMember.Role.OWNER and not is_platform_admin(request.user):
            return error_response(message="Cannot kick community owner.", status_code=status.HTTP_403_FORBIDDEN)

        membership.delete()
        logger.info(f"User {user_id} kicked from community {community_id} for: {reason}")
        return success_response(message="User kicked from community successfully.")


class BanUserView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CommunityBanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data["user_id"]
        community_id = serializer.validated_data["community_id"]
        ban_type = serializer.validated_data["ban_type"]
        duration_days = serializer.validated_data.get("duration_days")
        reason = serializer.validated_data.get("reason", "")

        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return error_response(message="Community not found.", status_code=status.HTTP_404_NOT_FOUND)

        if not is_community_admin_or_higher(request.user, community):
            return error_response(message="Only community admins and above can ban users.", status_code=status.HTTP_403_FORBIDDEN)

        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return error_response(message="User not found.", status_code=status.HTTP_404_NOT_FOUND)

        expires_at = None
        if ban_type == "temporary" and duration_days:
            expires_at = timezone.now() + timedelta(days=duration_days)

        # 1. Add CommunityBan
        CommunityBan.objects.update_or_create(
            user=target_user,
            community=community,
            defaults={
                "banned_by": request.user,
                "ban_type": ban_type,
                "reason": reason,
                "expires_at": expires_at,
            }
        )

        # 2. Kick them from the community
        CommunityMember.objects.filter(community=community, user=target_user).delete()
        return success_response(message="User banned from community successfully.")


class UnbanUserView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_id = request.data.get("user_id")
        community_id = request.data.get("community_id")
        if not user_id or not community_id:
            return error_response(message="user_id and community_id are required.", status_code=status.HTTP_400_BAD_REQUEST)

        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return error_response(message="Community not found.", status_code=status.HTTP_404_NOT_FOUND)

        if not is_community_admin_or_higher(request.user, community):
            return error_response(message="Only community admins and above can unban users.", status_code=status.HTTP_403_FORBIDDEN)

        CommunityBan.objects.filter(user_id=user_id, community=community).delete()
        return success_response(message="User unbanned successfully.")


class AdminDashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_platform_moderator(request.user):
            return error_response(message="Platform moderator role required.", status_code=status.HTTP_403_FORBIDDEN)

        now = timezone.now()
        active_mutes = UserMute.objects.filter(
            Q(expires_at__gt=now) | Q(expires_at__isnull=True)
        ).count()

        stats = {
            "total_reports": Report.objects.count(),
            "pending_reports": Report.objects.filter(status="pending").count(),
            "active_bans": CommunityBan.objects.count(),
            "active_mutes": active_mutes,
            "message_audit_logs": MessageAuditLog.objects.count(),
        }
        return success_response(data=stats, message="Stats retrieved successfully.")


class MessageAuditLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_platform_moderator(request.user):
            return error_response(message="Platform moderator role required.", status_code=status.HTTP_403_FORBIDDEN)

        qs = MessageAuditLog.objects.select_related("author", "performed_by").all()
        # Filter by action or author
        action_filter = request.query_params.get("action")
        author_id = request.query_params.get("author_id")
        if action_filter:
            qs = qs.filter(action=action_filter)
        if author_id:
            qs = qs.filter(author_id=author_id)

        serializer = MessageAuditLogSerializer(qs, many=True)
        return success_response(data=serializer.data, message="Message audit logs retrieved.")
