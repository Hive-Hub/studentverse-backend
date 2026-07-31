from __future__ import annotations

from rest_framework import permissions
from apps.communities.models import CommunityMember


class IsCommunityOwner(permissions.BasePermission):
    """Allows access only to the community owner."""

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or request.user.is_anonymous:
            return False
        # obj is a Community instance
        return obj.memberships.filter(
            user=request.user, role=CommunityMember.Role.OWNER
        ).exists()


class IsCommunityAdminOrOwner(permissions.BasePermission):
    """Allows access only to community admins or the owner."""

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or request.user.is_anonymous:
            return False
        return obj.memberships.filter(
            user=request.user,
            role__in=[CommunityMember.Role.OWNER, CommunityMember.Role.ADMIN],
        ).exists()


class IsCommunityModeratorOrHigher(permissions.BasePermission):
    """Allows access only to community moderators, admins, or the owner."""

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or request.user.is_anonymous:
            return False
        return obj.memberships.filter(
            user=request.user,
            role__in=[
                CommunityMember.Role.OWNER,
                CommunityMember.Role.ADMIN,
                CommunityMember.Role.MODERATOR,
            ],
        ).exists()


class IsCommunityMember(permissions.BasePermission):
    """Allows access only to members of the community."""

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or request.user.is_anonymous:
            return False
        return obj.memberships.filter(user=request.user).exists()


class IsChannelAccessAllowed(permissions.BasePermission):
    """
    Enforces access controls for channels:
    - Read (retrieve): User must be a community member.
      If moderator_only, user must be Moderator or higher.
    - Write (create/update/delete): User must be Owner or Admin.
    """

    def has_permission(self, request, view) -> bool:
        if not request.user or request.user.is_anonymous:
            return False

        # If creating a channel, check permissions on the target community
        if view.action == "create":
            community_ref = request.data.get("community")
            if not community_ref:
                return True  # Let serializer throw required field error

            from apps.communities.models import Community
            try:
                if str(community_ref).isdigit():
                    community = Community.objects.get(pk=community_ref)
                else:
                    community = Community.objects.get(slug=community_ref)
            except Community.DoesNotExist:
                return False

            # Check if user is owner or admin in this community
            return community.memberships.filter(
                user=request.user,
                role__in=[CommunityMember.Role.OWNER, CommunityMember.Role.ADMIN]
            ).exists()

        return True

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or request.user.is_anonymous:
            return False

        # obj is a Channel instance
        community = obj.community
        membership = community.memberships.filter(user=request.user).first()
        if not membership:
            return False

        # Write actions: Update / Delete
        if request.method not in permissions.SAFE_METHODS:
            return membership.role in [CommunityMember.Role.OWNER, CommunityMember.Role.ADMIN]

        # Read actions: Retrieve
        if obj.permission_type == "moderator_only":
            return membership.role in [
                CommunityMember.Role.OWNER,
                CommunityMember.Role.ADMIN,
                CommunityMember.Role.MODERATOR,
            ]

        return True

