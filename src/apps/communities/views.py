from __future__ import annotations

from datetime import timedelta
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.responses import error_response, success_response
from apps.communities.models import Community, CommunityMember, Channel
from apps.communities.permissions import (
    IsCommunityAdminOrOwner,
    IsCommunityMember,
    IsCommunityOwner,
    IsChannelAccessAllowed,
)
from apps.communities.serializers import (
    CommunityCreateSerializer,
    CommunityMemberRoleUpdateSerializer,
    CommunityMemberSerializer,
    CommunitySerializer,
    ChannelSerializer,
    ChannelCreateSerializer,
    ChannelUpdateSerializer,
)


class CommunityViewSet(viewsets.ModelViewSet):
    lookup_field = "slug"
    filter_backends = [SearchFilter]
    search_fields = ["name", "description"]

    def get_serializer_class(self):
        if self.action == "create":
            return CommunityCreateSerializer
        return CommunitySerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Community.objects.all()

        # Enforce list visibility:
        # - Anonymous users see only public communities.
        # - Authenticated users see public ones OR private ones they have joined.
        # We only apply this on 'list' so detail actions can resolve private objects
        # and throw proper 403/validation responses rather than 404s.
        if self.action == "list":
            if not user or user.is_anonymous:
                queryset = queryset.filter(is_public=True)
            else:
                queryset = queryset.filter(
                    Q(is_public=True) | Q(memberships__user=user)
                ).distinct()

        # Filter by public/private query param if provided
        is_public_param = self.request.query_params.get("is_public")
        if is_public_param is not None:
            is_public_bool = is_public_param.lower() in ("true", "1")
            queryset = queryset.filter(is_public=is_public_bool)

        # Annotate statistics for performant listing
        queryset = queryset.annotate(
            members_count=Count("memberships", distinct=True),
            admins_count=Count(
                "memberships",
                filter=Q(memberships__role=CommunityMember.Role.ADMIN),
                distinct=True,
            ),
            moderators_count=Count(
                "memberships",
                filter=Q(memberships__role=CommunityMember.Role.MODERATOR),
                distinct=True,
            ),
        )
        return queryset

    def get_permissions(self):
        if self.action in ["update", "partial_update"]:
            return [IsAuthenticated(), IsCommunityAdminOrOwner()]
        elif self.action == "destroy":
            return [IsAuthenticated(), IsCommunityOwner()]
        elif self.action == "create":
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            data=serializer.data,
            message="Communities list retrieved successfully."
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            # Create community
            community = serializer.save()
            # Assign creator as Owner
            CommunityMember.objects.create(
                community=community,
                user=request.user,
                role=CommunityMember.Role.OWNER
            )
            
        # Re-fetch to populate annotations
        refetched = self.get_queryset().get(pk=community.pk)
        response_serializer = CommunitySerializer(refetched, context={"request": request})
        return success_response(
            data=response_serializer.data,
            message="Community created successfully.",
            status_code=status.HTTP_201_CREATED
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Double check private community membership access
        if not instance.is_public and not instance.memberships.filter(user=request.user).exists():
            return error_response(
                message="Access denied. This is a private community.",
                status_code=status.HTTP_403_FORBIDDEN
            )
            
        # Log recently visited
        from apps.search.services import log_visited_entity
        log_visited_entity(request.user, "community", instance.id, instance.name)
            
        serializer = self.get_serializer(instance)
        return success_response(
            data=serializer.data,
            message="Community details retrieved successfully."
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Save updates
        serializer.save()
        
        # Re-fetch to populate annotations
        refetched = self.get_queryset().get(pk=instance.pk)
        response_serializer = CommunitySerializer(refetched, context={"request": request})
        return success_response(
            data=response_serializer.data,
            message="Community updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return success_response(
            message="Community deleted successfully.",
            status_code=status.HTTP_200_OK
        )

    # --- Custom Actions ---

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def join(self, request, slug=None):
        community = self.get_object()
        
        # Check if already a member
        if community.memberships.filter(user=request.user).exists():
            return error_response(
                message="You are already a member of this community.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Check if user is banned
        from apps.moderation.models import CommunityBan
        active_ban = CommunityBan.objects.filter(
            user=request.user,
            community=community
        ).filter(
            Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)
        ).exists()
        if active_ban:
            return error_response(
                message="You are banned from this community.",
                status_code=status.HTTP_403_FORBIDDEN
            )

        # Check private community invite code requirements
        if not community.is_public:
            invite_code = request.data.get("invite_code")
            if not invite_code or invite_code != community.invite_code:
                return error_response(
                    message="Invalid or missing invite code for this private community.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )

        # Add user as a Member
        membership = CommunityMember.objects.create(
            community=community,
            user=request.user,
            role=CommunityMember.Role.MEMBER
        )
        
        serializer = CommunityMemberSerializer(membership)
        return success_response(
            data=serializer.data,
            message=f"Successfully joined {community.name}!"
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsCommunityMember])
    def leave(self, request, slug=None):
        community = self.get_object()
        membership = community.memberships.get(user=request.user)

        # Owner cannot leave without transferring ownership
        if membership.role == CommunityMember.Role.OWNER:
            return error_response(
                message="Community owners cannot leave without transferring ownership first.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        membership.delete()
        return success_response(
            message=f"You have successfully left {community.name}."
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsCommunityAdminOrOwner], url_path="invite/reset")
    def invite_reset(self, request, slug=None):
        community = self.get_object()
        
        # Generate new invite code
        community.invite_code = "" # Forces regenerate in save()
        community.save()
        
        return success_response(
            data={"invite_code": community.invite_code},
            message="Community invite code regenerated successfully."
        )

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, IsCommunityMember])
    def statistics(self, request, slug=None):
        community = self.get_object()
        
        # Total counts
        total_members = community.members.count()
        
        # Role distribution counts
        memberships = community.memberships.all()
        roles_count = {
            CommunityMember.Role.OWNER: memberships.filter(role=CommunityMember.Role.OWNER).count(),
            CommunityMember.Role.ADMIN: memberships.filter(role=CommunityMember.Role.ADMIN).count(),
            CommunityMember.Role.MODERATOR: memberships.filter(role=CommunityMember.Role.MODERATOR).count(),
            CommunityMember.Role.MEMBER: memberships.filter(role=CommunityMember.Role.MEMBER).count(),
        }

        # Activity - joined in last 7 days
        seven_days_ago = timezone.now() - timedelta(days=7)
        joined_recent = memberships.filter(joined_at__gte=seven_days_ago).count()

        stats_data = {
            "members_count": total_members,
            "role_distribution": roles_count,
            "joined_last_7_days": joined_recent
        }

        return success_response(
            data=stats_data,
            message="Community statistics retrieved successfully."
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsCommunityOwner], url_path="transfer-ownership")
    def transfer_ownership(self, request, slug=None):
        community = self.get_object()
        target_user_id = request.data.get("target_user_id")

        if not target_user_id:
            return error_response(
                message="target_user_id is required.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Get current owner membership
        owner_membership = community.memberships.get(user=request.user)

        # Get target member membership
        try:
            target_membership = community.memberships.get(user_id=target_user_id)
        except CommunityMember.DoesNotExist:
            return error_response(
                message="Target user is not a member of this community.",
                status_code=status.HTTP_404_NOT_FOUND
            )

        if target_membership.user == request.user:
            return error_response(
                message="You are already the owner of this community.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Elevate target to owner
            target_membership.role = CommunityMember.Role.OWNER
            target_membership.save()
            # Demote current owner to admin
            owner_membership.role = CommunityMember.Role.ADMIN
            owner_membership.save()

        return success_response(
            message=f"Ownership of {community.name} successfully transferred to user id {target_user_id}."
        )

    @action(detail=True, methods=["get", "patch"], permission_classes=[IsAuthenticated, IsCommunityMember], url_path="members(?:/(?P<member_id>[^/.]+))?")
    def members(self, request, slug=None, member_id=None):
        community = self.get_object()

        # --- GET: List Members ---
        if request.method == "GET":
            memberships = community.memberships.all().select_related("user", "user__profile")
            
            # Allow filtering by role query parameter
            role_filter = request.query_params.get("role")
            if role_filter:
                memberships = memberships.filter(role=role_filter)

            serializer = CommunityMemberSerializer(memberships, many=True)
            return success_response(
                data=serializer.data,
                message="Community members list retrieved successfully."
            )

        # --- PATCH: Update Member Role ---
        if request.method == "PATCH":
            if not member_id:
                return error_response(
                    message="Member ID is required in the path to update a role.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            # Check promotion permissions
            caller_membership = community.memberships.filter(user=request.user).first()
            if not caller_membership or caller_membership.role not in [CommunityMember.Role.OWNER, CommunityMember.Role.ADMIN]:
                return error_response(
                    message="You must be an owner or admin to promote/demote members.",
                    status_code=status.HTTP_403_FORBIDDEN
                )

            try:
                target_membership = community.memberships.get(id=member_id)
            except CommunityMember.DoesNotExist:
                return error_response(
                    message="Community member record not found.",
                    status_code=status.HTTP_404_NOT_FOUND
                )

            # Restrict modifying own role
            if target_membership.user == request.user:
                return error_response(
                    message="You cannot change your own role.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            # Restrict modifying Owner
            if target_membership.role == CommunityMember.Role.OWNER:
                return error_response(
                    message="The community owner's role cannot be modified.",
                    status_code=status.HTTP_403_FORBIDDEN
                )

            # Restrict Admin modifying other Admins
            if caller_membership.role == CommunityMember.Role.ADMIN and target_membership.role == CommunityMember.Role.ADMIN:
                return error_response(
                    message="Admins cannot promote/demote other admins.",
                    status_code=status.HTTP_403_FORBIDDEN
                )

            serializer = CommunityMemberRoleUpdateSerializer(target_membership, data=request.data)
            serializer.is_valid(raise_exception=True)
            new_role = serializer.validated_data["role"]

            # Only Owner can promote someone to Admin
            if new_role == CommunityMember.Role.ADMIN and caller_membership.role != CommunityMember.Role.OWNER:
                return error_response(
                    message="Only the community owner can promote a member to Admin.",
                    status_code=status.HTTP_403_FORBIDDEN
                )

            serializer.save()
            return success_response(
                data=CommunityMemberSerializer(target_membership).data,
                message="Member role updated successfully."
            )


class ChannelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsChannelAccessAllowed]

    def get_serializer_class(self):
        if self.action == "create":
            return ChannelCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return ChannelUpdateSerializer
        return ChannelSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or user.is_anonymous:
            return Channel.objects.none()

        # Retrieve memberships of this user
        user_memberships = CommunityMember.objects.filter(user=user)
        community_ids = user_memberships.values_list("community_id", flat=True)

        # Base filter: Channels belonging to communities the user has joined
        queryset = Channel.objects.filter(community_id__in=community_ids)

        # Filter out moderator_only channels if user's role is just 'member'
        member_community_ids = user_memberships.filter(
            role=CommunityMember.Role.MEMBER
        ).values_list("community_id", flat=True)

        queryset = queryset.exclude(
            community_id__in=member_community_ids,
            permission_type=Channel.PermissionType.MODERATOR_ONLY
        )

        # Filter parameters
        community_slug = self.request.query_params.get("community")
        if community_slug:
            queryset = queryset.filter(community__slug=community_slug)

        channel_type = self.request.query_params.get("channel_type")
        if channel_type:
            queryset = queryset.filter(channel_type=channel_type)

        is_pinned = self.request.query_params.get("is_pinned")
        if is_pinned is not None:
            queryset = queryset.filter(is_pinned=is_pinned.lower() in ("true", "1"))

        is_archived = self.request.query_params.get("is_archived")
        if is_archived is not None:
            queryset = queryset.filter(is_archived=is_archived.lower() in ("true", "1"))

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            data=serializer.data,
            message="Channels list retrieved successfully."
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channel = serializer.save()

        response_serializer = ChannelSerializer(channel, context={"request": request})
        return success_response(
            data=response_serializer.data,
            message="Channel created successfully.",
            status_code=status.HTTP_201_CREATED
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response(
            data=serializer.data,
            message="Channel details retrieved successfully."
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        channel = serializer.save()

        response_serializer = ChannelSerializer(channel, context={"request": request})
        return success_response(
            data=response_serializer.data,
            message="Channel updated successfully."
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return success_response(
            message="Channel deleted successfully.",
            status_code=status.HTTP_200_OK
        )

