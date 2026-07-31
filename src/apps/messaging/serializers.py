from __future__ import annotations

from collections import defaultdict
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from apps.communities.models import Channel, CommunityMember
from apps.communities.serializers import UserMiniSerializer
from apps.messaging.models import Message, MessageAttachment, MessageReaction
from apps.messaging.validators import validate_emoji, validate_attachment_file

User = get_user_model()


# ---------------------------------------------------------------------------
# Attachment
# ---------------------------------------------------------------------------

class MessageAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = ("id", "file_url", "file_name", "file_size", "mime_type", "uploaded_at")

    def get_file_url(self, obj) -> str:
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else ""


class MessageAttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(validators=[validate_attachment_file])

    def validate_file(self, value):
        validate_attachment_file(value)
        return value


# ---------------------------------------------------------------------------
# Reaction
# ---------------------------------------------------------------------------

class MessageReactionSummarySerializer(serializers.Serializer):
    """Groups reactions by emoji, returning count and whether the caller reacted."""
    emoji = serializers.CharField()
    count = serializers.IntegerField()
    reacted_by_me = serializers.BooleanField()


# ---------------------------------------------------------------------------
# Message (read)
# ---------------------------------------------------------------------------

class MessageSerializer(serializers.ModelSerializer):
    author = UserMiniSerializer(read_only=True)
    attachments = MessageAttachmentSerializer(many=True, read_only=True)
    reactions = serializers.SerializerMethodField()
    reply_count = serializers.IntegerField(read_only=True, default=0)
    parent_id = serializers.PrimaryKeyRelatedField(source="parent", read_only=True)
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    mention_ids = serializers.PrimaryKeyRelatedField(source="mentions", many=True, read_only=True)

    class Meta:
        model = Message
        fields = (
            "id",
            "channel",
            "author",
            "content",
            "parent_id",
            "gif_url",
            "mention_ids",
            "attachments",
            "reactions",
            "reply_count",
            "is_pinned",
            "is_edited",
            "edited_at",
            "can_edit",
            "can_delete",
            "created_at",
            "updated_at",
        )

    def get_reactions(self, obj) -> list:
        request = self.context.get("request")
        caller = request.user if request else None
        # Group reactions by emoji
        grouped: dict = defaultdict(lambda: {"count": 0, "reacted_by_me": False})
        for reaction in obj.reactions.all():
            entry = grouped[reaction.emoji]
            entry["count"] += 1
            if caller and reaction.user_id == caller.id:
                entry["reacted_by_me"] = True
        return [
            {"emoji": emoji, "count": data["count"], "reacted_by_me": data["reacted_by_me"]}
            for emoji, data in grouped.items()
        ]

    def get_can_edit(self, obj) -> bool:
        request = self.context.get("request")
        if not request:
            return False
        return obj.author_id == request.user.id

    def get_can_delete(self, obj) -> bool:
        request = self.context.get("request")
        if not request:
            return False
        if obj.author_id == request.user.id:
            return True
        try:
            membership = CommunityMember.objects.get(
                community=obj.channel.community,
                user=request.user,
            )
            return membership.role in (
                CommunityMember.Role.OWNER,
                CommunityMember.Role.ADMIN,
                CommunityMember.Role.MODERATOR,
            )
        except CommunityMember.DoesNotExist:
            return False


# ---------------------------------------------------------------------------
# Message Create
# ---------------------------------------------------------------------------

class MessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(required=False, allow_blank=True, default="")
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.all(),
        required=False,
        allow_null=True,
    )
    gif_url = serializers.URLField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        content = attrs.get("content", "").strip()
        gif_url = attrs.get("gif_url", "").strip()
        # At least one of content, gif_url must be provided (attachments uploaded separately)
        if not content and not gif_url:
            raise serializers.ValidationError(
                "A message must have content or a GIF URL. Attach files after creating the message."
            )

        # Moderation checks
        from apps.moderation.validators import validate_moderated_content, is_user_muted
        request = self.context.get("request")
        user = request.user if request else None
        if user and not user.is_anonymous:
            channel_id = self.context.get("channel_id")
            community = None
            if channel_id:
                try:
                    community = Channel.objects.get(pk=channel_id).community
                except Exception:
                    pass
            if is_user_muted(user, community=community):
                raise serializers.ValidationError("You are currently muted and cannot post content.")

        if content:
            validate_moderated_content(content, user=user)

        return attrs

    def validate_parent_id(self, parent):
        channel_id = self.context.get("channel_id")
        if parent and str(parent.channel_id) != str(channel_id):
            raise serializers.ValidationError("Parent message must belong to the same channel.")
        # Thread nesting: only top-level messages can be parents
        if parent and parent.parent_id is not None:
            raise serializers.ValidationError("Cannot reply to a thread reply. Reply to the top-level message.")
        return parent

    def create(self, validated_data):
        request = self.context["request"]
        channel_id = self.context["channel_id"]
        channel = Channel.objects.get(pk=channel_id)
        message = Message.objects.create(
            channel=channel,
            author=request.user,
            content=validated_data.get("content", ""),
            parent=validated_data.get("parent_id"),
            gif_url=validated_data.get("gif_url", ""),
        )
        message.extract_and_set_mentions()
        return message


# ---------------------------------------------------------------------------
# Message Update
# ---------------------------------------------------------------------------

class MessageUpdateSerializer(serializers.Serializer):
    content = serializers.CharField(required=True, allow_blank=False)

    def validate(self, attrs):
        content = attrs.get("content", "").strip()
        # Moderation checks
        from apps.moderation.validators import validate_moderated_content, is_user_muted
        request = self.context.get("request")
        user = request.user if request else None
        if user and not user.is_anonymous:
            community = None
            if self.instance and self.instance.channel:
                community = self.instance.channel.community
            if is_user_muted(user, community=community):
                raise serializers.ValidationError("You are currently muted and cannot post content.")

        if content:
            validate_moderated_content(content, user=user)

        return attrs

    def update(self, instance, validated_data):
        instance.content = validated_data["content"]
        instance.is_edited = True
        instance.edited_at = timezone.now()
        instance.save(update_fields=["content", "is_edited", "edited_at", "updated_at"])
        instance.extract_and_set_mentions()
        return instance


# ---------------------------------------------------------------------------
# Reaction
# ---------------------------------------------------------------------------

class ReactionCreateSerializer(serializers.Serializer):
    emoji = serializers.CharField(max_length=10, validators=[validate_emoji])
