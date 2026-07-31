from __future__ import annotations

from rest_framework.permissions import BasePermission, SAFE_METHODS
from apps.communities.models import CommunityMember, Channel


def _get_membership(user, community):
    """Return the user membership for a community or None."""
    try:
        return CommunityMember.objects.get(community=community, user=user)
    except CommunityMember.DoesNotExist:
        return None


def _is_moderator_or_higher(membership) -> bool:
    if membership is None:
        return False
    return membership.role in (
        CommunityMember.Role.OWNER,
        CommunityMember.Role.ADMIN,
        CommunityMember.Role.MODERATOR,
    )


def _is_admin_or_owner(membership) -> bool:
    if membership is None:
        return False
    return membership.role in (
        CommunityMember.Role.OWNER,
        CommunityMember.Role.ADMIN,
    )


class IsChannelMember(BasePermission):
    """
    Allows access only to users who are members of the channel s community.
    Requires view.kwargs["channel_id"] to be set.
    """
    message = "You must be a member of this community to access its messages."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        channel_id = view.kwargs.get("channel_id")
        if not channel_id:
            return False
        try:
            channel = Channel.objects.select_related("community").get(pk=channel_id)
        except Channel.DoesNotExist:
            return False
        membership = _get_membership(request.user, channel.community)
        return membership is not None


class CanWriteToChannel(BasePermission):
    """
    Allows write operations only if the channel permits it.
    - READ_ONLY channels: only moderators/admins/owners can write.
    - MODERATOR_ONLY channels: only moderators/admins/owners can read or write.
    - WRITE channels: all members can write.
    Safe methods (GET/HEAD/OPTIONS) are always passed through to IsChannelMember.
    """
    message = "You do not have permission to write in this channel."

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True  # Read access controlled by IsChannelMember
        channel_id = view.kwargs.get("channel_id")
        if not channel_id:
            return False
        try:
            channel = Channel.objects.select_related("community").get(pk=channel_id)
        except Channel.DoesNotExist:
            return False
        membership = _get_membership(request.user, channel.community)
        if membership is None:
            return False
        if channel.permission_type == Channel.PermissionType.READ_ONLY:
            return _is_moderator_or_higher(membership)
        return True


class IsMessageAuthorOrModerator(BasePermission):
    """
    - PATCH (edit): only the message author.
    - DELETE: author, or moderator/admin/owner of the community.
    - PIN action: moderator/admin/owner only.
    Evaluated at object level.
    """
    message = "You do not have permission to modify this message."

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        community = obj.channel.community
        membership = _get_membership(request.user, community)
        if request.method == "DELETE" or view.action == "destroy":
            # Author can delete their own; moderator+ can delete any
            return obj.author == request.user or _is_moderator_or_higher(membership)
        if view.action in ("update", "partial_update"):
            # Only author can edit
            return obj.author == request.user
        if view.action == "pin":
            return _is_moderator_or_higher(membership)
        return obj.author == request.user
