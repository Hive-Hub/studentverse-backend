from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers
from apps.news.serializers import NewsAuthorSerializer
from .models import Event, EventSpeaker, EventSponsor, EventGalleryImage, EventRSVP, EventReminder, EventComment

User = get_user_model()


class EventSpeakerSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventSpeaker
        fields = ("id", "name", "bio", "photo")


class EventSponsorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventSponsor
        fields = ("id", "name", "logo", "website")


class EventGalleryImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventGalleryImage
        fields = ("id", "image", "created_at")


class EventRSVPSerializer(serializers.ModelSerializer):
    user = NewsAuthorSerializer(read_only=True)

    class Meta:
        model = EventRSVP
        fields = ("id", "user", "status", "attended", "joined_at")


class EventCommentSerializer(serializers.ModelSerializer):
    user = NewsAuthorSerializer(read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = EventComment
        fields = ("id", "event", "user", "parent", "content", "created_at", "updated_at", "replies")
        read_only_fields = ("event", "user", "created_at", "updated_at")

    def validate(self, attrs):
        content = attrs.get("content", "").strip()
        from apps.moderation.validators import validate_moderated_content, is_user_muted
        request = self.context.get("request")
        user = request.user if request else None
        if user and not user.is_anonymous:
            event = attrs.get("event") or self.context.get("event")
            community = event.community if event else None
            if is_user_muted(user, community=community):
                raise serializers.ValidationError("You are currently muted and cannot post comments.")
        if content:
            validate_moderated_content(content, user=user)
        return attrs

    def get_replies(self, obj: EventComment) -> list[dict]:
        replies = obj.replies.all()
        return EventCommentSerializer(replies, many=True, context=self.context).data


class EventSerializer(serializers.ModelSerializer):
    author = NewsAuthorSerializer(read_only=True)
    speakers = EventSpeakerSerializer(many=True, read_only=True)
    sponsors = EventSponsorSerializer(many=True, read_only=True)
    gallery = EventGalleryImageSerializer(many=True, read_only=True)
    
    comments_count = serializers.SerializerMethodField()
    rsvps_count = serializers.SerializerMethodField()
    joined_count = serializers.SerializerMethodField()
    waiting_list_count = serializers.SerializerMethodField()
    
    is_joined = serializers.SerializerMethodField()
    is_waitlisted = serializers.SerializerMethodField()
    has_attended = serializers.SerializerMethodField()
    
    community_name = serializers.CharField(source="community.name", read_only=True)
    community_slug = serializers.CharField(source="community.slug", read_only=True)

    class Meta:
        model = Event
        fields = (
            "id",
            "title",
            "description",
            "scope",
            "community",
            "community_name",
            "community_slug",
            "college",
            "event_type",
            "location",
            "start_time",
            "end_time",
            "banner",
            "seats",
            "qr_code_key",
            "author",
            "is_blocked",
            "speakers",
            "sponsors",
            "gallery",
            "comments_count",
            "rsvps_count",
            "joined_count",
            "waiting_list_count",
            "is_joined",
            "is_waitlisted",
            "has_attended",
            "created_at",
            "updated_at",
        )

    def get_comments_count(self, obj: Event) -> int:
        return obj.comments.count()

    def get_rsvps_count(self, obj: Event) -> int:
        return obj.rsvps.count()

    def get_joined_count(self, obj: Event) -> int:
        return obj.rsvps.filter(status=EventRSVP.Status.JOINED).count()

    def get_waiting_list_count(self, obj: Event) -> int:
        return obj.rsvps.filter(status=EventRSVP.Status.WAITING_LIST).count()

    def _get_rsvp(self, obj: Event) -> EventRSVP | None:
        request = self.context.get("request")
        if not request or not request.user or request.user.is_anonymous:
            return None
        return obj.rsvps.filter(user=request.user).first()

    def get_is_joined(self, obj: Event) -> bool:
        rsvp = self._get_rsvp(obj)
        return rsvp is not None and rsvp.status == EventRSVP.Status.JOINED

    def get_is_waitlisted(self, obj: Event) -> bool:
        rsvp = self._get_rsvp(obj)
        return rsvp is not None and rsvp.status == EventRSVP.Status.WAITING_LIST

    def get_has_attended(self, obj: Event) -> bool:
        rsvp = self._get_rsvp(obj)
        return rsvp is not None and rsvp.attended


class EventCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = (
            "id",
            "title",
            "description",
            "scope",
            "community",
            "college",
            "event_type",
            "location",
            "start_time",
            "end_time",
            "banner",
            "seats",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate(self, attrs):
        scope = attrs.get("scope", getattr(self.instance, "scope", Event.Scope.PLATFORM))
        community = attrs.get("community", getattr(self.instance, "community", None))
        college = attrs.get("college", getattr(self.instance, "college", None))

        if scope == Event.Scope.COMMUNITY and not community:
            raise serializers.ValidationError({"community": "Community is required for community scope."})
        if scope == Event.Scope.COLLEGE and not college:
            raise serializers.ValidationError({"college": "College is required for college scope."})

        # Ensure start_time < end_time
        start_time = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError({"end_time": "End time must be after start time."})

        # Moderation checks
        description = attrs.get("description", "").strip()
        title = attrs.get("title", "").strip()
        from apps.moderation.validators import validate_moderated_content, is_user_muted
        request = self.context.get("request")
        user = request.user if request else None
        if user and not user.is_anonymous:
            if is_user_muted(user, community=community):
                raise serializers.ValidationError("You are currently muted and cannot post events.")
        if description:
            validate_moderated_content(description, user=user)
        if title:
            validate_moderated_content(title, user=user)

        return attrs

    def to_representation(self, instance: Event) -> dict:
        return EventSerializer(instance, context=self.context).data
