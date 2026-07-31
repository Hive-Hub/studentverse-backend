from __future__ import annotations

import django.utils.timezone as timezone
from rest_framework import permissions
from apps.communities.models import CommunityMember


class IsNewsAuthorOrModeratorOrReadOnly(permissions.BasePermission):
    """
    Allow edit/delete only if:
    - User is a Platform Admin or Platform Moderator.
    - User is the author of the news.
    - If the news is community-scoped: User is an Owner, Admin, or Moderator in that community.
    - If the news is college-scoped: User is a Moderator or Admin and belongs to that college.
    """

    def has_read_permission(self, request, obj) -> bool:
        user_profile = getattr(request.user, "profile", None)
        user_role = user_profile.role if user_profile else "student"

        # Admin/Mod can read anything
        if user_role in ["admin", "moderator"]:
            return True

        if obj.is_blocked:
            return False

        if obj.status == "draft":
            return obj.author == request.user

        if obj.scheduled_publish_at and obj.scheduled_publish_at > timezone.now():
            return obj.author == request.user

        if obj.scope == "community" and obj.community:
            if not obj.community.is_public:
                return obj.community.memberships.filter(user=request.user).exists()

        if obj.scope == "college" and obj.college:
            if not user_profile or not user_profile.college or user_profile.college.lower() != obj.college.lower():
                return False

        return True

    def has_permission(self, request, view) -> bool:
        if not request.user or request.user.is_anonymous:
            return False
        
        # Read-only actions always allowed for authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
            
        # Create action requires some role other than student, or membership roles
        if view.action == "create":
            scope = request.data.get("scope", "platform")
            user_profile = getattr(request.user, "profile", None)
            user_role = user_profile.role if user_profile else "student"
            
            if scope == "platform":
                return user_role in ["admin", "moderator"]
            elif scope == "college":
                college = request.data.get("college")
                if not college:
                    return True  # let serializer raise 400 Bad Request
                if user_profile and user_profile.college and user_profile.college.lower() == college.lower():
                    return user_role in ["admin", "moderator"]
                return user_role == "admin"
            elif scope == "community":
                community_id = request.data.get("community")
                if not community_id:
                    return True  # let serializer raise 400 Bad Request
                
                from apps.communities.models import Community
                try:
                    if str(community_id).isdigit():
                        community = Community.objects.get(pk=community_id)
                    else:
                        community = Community.objects.get(slug=community_id)
                except Community.DoesNotExist:
                    return False
                
                return community.memberships.filter(
                    user=request.user,
                    role__in=[
                        CommunityMember.Role.OWNER,
                        CommunityMember.Role.ADMIN,
                        CommunityMember.Role.MODERATOR,
                    ]
                ).exists() or user_role in ["admin", "moderator"]
            
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or request.user.is_anonymous:
            return False

        # If action is read-only or a user interaction action, check read visibility
        if request.method in permissions.SAFE_METHODS or view.action in ["like", "bookmark", "report", "comments", "share"]:
            return self.has_read_permission(request, obj)
            
        user_profile = getattr(request.user, "profile", None)
        user_role = user_profile.role if user_profile else "student"
        
        # Platform Admin/Moderator can do anything
        if user_role in ["admin", "moderator"]:
            return True

        # Write actions: Edit, Update, Delete, Attachments, Publish
        if obj.author == request.user:
            return not obj.is_blocked
            
        if obj.scope == "community" and obj.community:
            return obj.community.memberships.filter(
                user=request.user,
                role__in=[
                    CommunityMember.Role.OWNER,
                    CommunityMember.Role.ADMIN,
                    CommunityMember.Role.MODERATOR,
                ]
            ).exists()
            
        if obj.scope == "college" and obj.college:
            if user_profile and user_profile.college and user_profile.college.lower() == obj.college.lower():
                return user_role in ["admin", "moderator"]

        return False


class IsCommentAuthorOrModeratorOrReadOnly(permissions.BasePermission):
    """
    Allows comments access:
    - Edit/Delete comment: comment author, news author, platform admin/mod, community owner/admin/mod (if community-scoped).
    """

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or request.user.is_anonymous:
            return False
            
        if request.method in permissions.SAFE_METHODS:
            return True
            
        if obj.user == request.user:
            return True
            
        user_profile = getattr(request.user, "profile", None)
        user_role = user_profile.role if user_profile else "student"
        
        if user_role in ["admin", "moderator"]:
            return True
            
        if obj.news.author == request.user:
            return True
            
        if obj.news.scope == "community" and obj.news.community:
            return obj.news.community.memberships.filter(
                user=request.user,
                role__in=[
                    CommunityMember.Role.OWNER,
                    CommunityMember.Role.ADMIN,
                    CommunityMember.Role.MODERATOR,
                ]
            ).exists()
            
        return False
