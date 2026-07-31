from __future__ import annotations

from django.db.models import Count, Q
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.responses import error_response, success_response
from apps.communities.models import Channel, CommunityMember
from apps.messaging.models import Message, MessageAttachment, MessageReaction
from apps.messaging.permissions import (
    IsChannelMember,
    CanWriteToChannel,
    IsMessageAuthorOrModerator,
)
from apps.messaging.serializers import (
    MessageSerializer,
    MessageCreateSerializer,
    MessageUpdateSerializer,
    MessageAttachmentUploadSerializer,
    ReactionCreateSerializer,
)
from apps.messaging.validators import validate_attachment_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_channel_or_404(channel_id):
    try:
        return Channel.objects.select_related("community").get(pk=channel_id)
    except Channel.DoesNotExist:
        return None


def _get_membership(user, community):
    try:
        return CommunityMember.objects.get(community=community, user=user)
    except CommunityMember.DoesNotExist:
        return None


def _is_moderator_or_higher(membership) -> bool:
    if not membership:
        return False
    return membership.role in (
        CommunityMember.Role.OWNER,
        CommunityMember.Role.ADMIN,
        CommunityMember.Role.MODERATOR,
    )


def _broadcast_reactions(message, channel_id):
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    from collections import defaultdict
    channel_layer = get_channel_layer()
    if channel_layer:
        grouped = defaultdict(lambda: {"count": 0})
        for r in message.reactions.all():
            grouped[r.emoji]["count"] += 1
        reactions_data = [
            {"emoji": emoji, "count": data["count"]}
            for emoji, data in grouped.items()
        ]
        async_to_sync(channel_layer.group_send)(
            f"channel_{channel_id}",
            {
                "type": "reaction_broadcast",
                "message_id": message.id,
                "reactions": reactions_data
            }
        )


# ---------------------------------------------------------------------------
# MessageViewSet
# ---------------------------------------------------------------------------

class MessageViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsChannelMember, CanWriteToChannel]

    def _get_message_queryset(self, channel):
        return (
            Message.objects.filter(channel=channel)
            .select_related("author", "channel__community")
            .prefetch_related("attachments", "reactions", "mentions")
            .annotate(reply_count=Count("thread_replies"))
        )

    def list(self, request, channel_id=None):
        channel = _get_channel_or_404(channel_id)
        if not channel:
            return error_response(message="Channel not found.", status_code=status.HTTP_404_NOT_FOUND)

        qs = self._get_message_queryset(channel).filter(parent__isnull=True)

        # Filters
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(content__icontains=search)

        pinned_only = request.query_params.get("pinned_only", "").lower()
        if pinned_only in ("true", "1"):
            qs = qs.filter(is_pinned=True)

        # Cursor-based pagination via ?before=<created_at ISO> and ?limit=<n>
        before = request.query_params.get("before")
        if before:
            qs = qs.filter(created_at__lt=before)

        limit = min(int(request.query_params.get("limit", 50)), 100)
        qs = qs.order_by("-created_at")[:limit]
        messages = list(reversed(list(qs)))

        serializer = MessageSerializer(messages, many=True, context={"request": request})
        return success_response(
            data=serializer.data,
            message="Messages retrieved successfully.",
            meta={"count": len(messages), "limit": limit},
        )

    def create(self, request, channel_id=None):
        channel = _get_channel_or_404(channel_id)
        if not channel:
            return error_response(message="Channel not found.", status_code=status.HTTP_404_NOT_FOUND)

        serializer = MessageCreateSerializer(
            data=request.data,
            context={"request": request, "channel_id": channel_id},
        )
        serializer.is_valid(raise_exception=True)
        message = serializer.save()

        out = MessageSerializer(message, context={"request": request})

        # Broadcast via Channels
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"channel_{channel_id}",
                {
                    "type": "chat_message",
                    "message": out.data
                }
            )

        return success_response(
            data=out.data,
            message="Message sent.",
            status_code=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, channel_id=None, pk=None):
        channel = _get_channel_or_404(channel_id)
        if not channel:
            return error_response(message="Channel not found.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            message = (
                Message.objects.filter(channel=channel)
                .select_related("author", "channel__community")
                .prefetch_related("attachments", "reactions", "mentions")
                .annotate(reply_count=Count("thread_replies"))
                .get(pk=pk)
            )
        except Message.DoesNotExist:
            return error_response(message="Message not found.", status_code=status.HTTP_404_NOT_FOUND)

        serializer = MessageSerializer(message, context={"request": request})
        return success_response(data=serializer.data, message="Message retrieved.")

    def partial_update(self, request, channel_id=None, pk=None):
        channel = _get_channel_or_404(channel_id)
        if not channel:
            return error_response(message="Channel not found.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            message = Message.objects.get(channel=channel, pk=pk)
        except Message.DoesNotExist:
            return error_response(message="Message not found.", status_code=status.HTTP_404_NOT_FOUND)

        # Object-level permission: only author can edit
        if message.author != request.user:
            return error_response(
                message="You can only edit your own messages.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = MessageUpdateSerializer(message, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()

        out = MessageSerializer(
            Message.objects.prefetch_related("attachments", "reactions", "mentions")
                           .annotate(reply_count=Count("thread_replies"))
                           .get(pk=updated.pk),
            context={"request": request},
        )

        # Broadcast via Channels
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"channel_{channel_id}",
                {
                    "type": "message_edited",
                    "message": out.data
                }
            )

        return success_response(data=out.data, message="Message updated.")

    def destroy(self, request, channel_id=None, pk=None):
        channel = _get_channel_or_404(channel_id)
        if not channel:
            return error_response(message="Channel not found.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            message = Message.objects.select_related("channel__community").get(channel=channel, pk=pk)
        except Message.DoesNotExist:
            return error_response(message="Message not found.", status_code=status.HTTP_404_NOT_FOUND)

        membership = _get_membership(request.user, channel.community)
        is_author = message.author == request.user
        is_mod = _is_moderator_or_higher(membership)

        if not is_author and not is_mod:
            return error_response(
                message="You do not have permission to delete this message.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        message.delete()

        # Broadcast via Channels
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"channel_{channel_id}",
                {
                    "type": "message_deleted",
                    "message_id": int(pk)
                }
            )

        return success_response(message="Message deleted.", status_code=status.HTTP_200_OK)

    @action(detail=True, methods=["post", "delete"], url_path="react")
    def react(self, request, channel_id=None, pk=None):
        channel = _get_channel_or_404(channel_id)
        if not channel:
            return error_response(message="Channel not found.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            message = Message.objects.get(channel=channel, pk=pk)
        except Message.DoesNotExist:
            return error_response(message="Message not found.", status_code=status.HTTP_404_NOT_FOUND)

        if request.method == "POST":
            from apps.moderation.validators import is_user_muted
            if is_user_muted(request.user, community=channel.community):
                return error_response(
                    message="You are currently muted and cannot post reactions.",
                    status_code=status.HTTP_403_FORBIDDEN
                )
            serializer = ReactionCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            emoji = serializer.validated_data["emoji"]
            reaction, created = MessageReaction.objects.get_or_create(
                message=message, user=request.user, emoji=emoji
            )
            if not created:
                return error_response(
                    message="You have already reacted with this emoji.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            
            # Broadcast via Channels
            _broadcast_reactions(message, channel_id)

            return success_response(
                data={"emoji": emoji, "message_id": message.id},
                message="Reaction added.",
                status_code=status.HTTP_201_CREATED,
            )

        elif request.method == "DELETE":
            emoji = request.data.get("emoji") or request.query_params.get("emoji")
            if not emoji:
                return error_response(message="emoji is required.", status_code=status.HTTP_400_BAD_REQUEST)
            deleted, _ = MessageReaction.objects.filter(
                message=message, user=request.user, emoji=emoji
            ).delete()
            if not deleted:
                return error_response(message="Reaction not found.", status_code=status.HTTP_404_NOT_FOUND)
            
            # Broadcast via Channels
            _broadcast_reactions(message, channel_id)

            return success_response(message="Reaction removed.")

    @action(detail=True, methods=["post"], url_path="pin")
    def pin(self, request, channel_id=None, pk=None):
        channel = _get_channel_or_404(channel_id)
        if not channel:
            return error_response(message="Channel not found.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            message = Message.objects.select_related("channel__community").get(channel=channel, pk=pk)
        except Message.DoesNotExist:
            return error_response(message="Message not found.", status_code=status.HTTP_404_NOT_FOUND)

        membership = _get_membership(request.user, channel.community)
        if not _is_moderator_or_higher(membership):
            return error_response(
                message="Only moderators and above can pin messages.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        message.is_pinned = not message.is_pinned
        message.save(update_fields=["is_pinned", "updated_at"])
        state = "pinned" if message.is_pinned else "unpinned"

        # Broadcast via Channels
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"channel_{channel_id}",
                {
                    "type": "pinned_broadcast",
                    "message_id": message.id,
                    "is_pinned": message.is_pinned
                }
            )

        return success_response(
            data={"id": message.id, "is_pinned": message.is_pinned},
            message=f"Message {state}.",
        )

    @action(detail=True, methods=["get"], url_path="thread")
    def thread(self, request, channel_id=None, pk=None):
        channel = _get_channel_or_404(channel_id)
        if not channel:
            return error_response(message="Channel not found.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            parent = Message.objects.get(channel=channel, pk=pk)
        except Message.DoesNotExist:
            return error_response(message="Message not found.", status_code=status.HTTP_404_NOT_FOUND)

        replies = (
            Message.objects.filter(parent=parent)
            .select_related("author", "channel__community")
            .prefetch_related("attachments", "reactions", "mentions")
            .annotate(reply_count=Count("thread_replies"))
            .order_by("created_at")
        )

        # Simple limit
        limit = min(int(request.query_params.get("limit", 50)), 100)
        replies = replies[:limit]

        serializer = MessageSerializer(replies, many=True, context={"request": request})
        return success_response(
            data=serializer.data,
            message="Thread replies retrieved.",
            meta={"parent_id": parent.id, "count": len(serializer.data)},
        )


# ---------------------------------------------------------------------------
# MessageAttachmentViewSet
# ---------------------------------------------------------------------------

class MessageAttachmentViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def create(self, request, message_id=None):
        """Upload one or more attachments to a message."""
        try:
            message = Message.objects.select_related("channel__community", "author").get(pk=message_id)
        except Message.DoesNotExist:
            return error_response(message="Message not found.", status_code=status.HTTP_404_NOT_FOUND)

        # Only the message author can add attachments
        if message.author != request.user:
            return error_response(
                message="Only the message author can add attachments.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        files = request.FILES.getlist("files") or ([request.FILES.get("file")] if request.FILES.get("file") else [])
        if not files:
            return error_response(message="No files provided.", status_code=status.HTTP_400_BAD_REQUEST)

        if len(files) > 10:
            return error_response(message="Maximum 10 files per message.", status_code=status.HTTP_400_BAD_REQUEST)

        created = []
        for f in files:
            try:
                validate_attachment_file(f)
            except Exception as e:
                return error_response(message=str(e), status_code=status.HTTP_400_BAD_REQUEST)

            attachment = MessageAttachment.objects.create(
                message=message,
                file=f,
                file_name=f.name,
                file_size=f.size,
                mime_type=getattr(f, "content_type", ""),
            )
            created.append({
                "id": attachment.id,
                "file_name": attachment.file_name,
                "file_size": attachment.file_size,
                "mime_type": attachment.mime_type,
            })

        return success_response(
            data=created,
            message=f"{len(created)} attachment(s) uploaded.",
            status_code=status.HTTP_201_CREATED,
        )

    def destroy(self, request, message_id=None, pk=None):
        """Delete an attachment from a message."""
        try:
            attachment = MessageAttachment.objects.select_related(
                "message__author", "message__channel__community"
            ).get(pk=pk, message_id=message_id)
        except MessageAttachment.DoesNotExist:
            return error_response(message="Attachment not found.", status_code=status.HTTP_404_NOT_FOUND)

        if attachment.message.author != request.user:
            membership = _get_membership(request.user, attachment.message.channel.community)
            if not _is_moderator_or_higher(membership):
                return error_response(
                    message="You do not have permission to delete this attachment.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        attachment.delete()
        return success_response(message="Attachment deleted.")
