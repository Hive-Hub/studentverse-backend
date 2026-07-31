from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers
from apps.communities.serializers import UserMiniSerializer
from .models import Tag, News, NewsLike, NewsBookmark, NewsReport, NewsComment, NewsAttachment

User = get_user_model()


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name")


class NewsAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsAttachment
        fields = ("id", "file", "file_name", "file_size", "mime_type", "created_at")


class NewsAuthorSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source="profile.display_name", read_only=True)
    profile_photo = serializers.ImageField(source="profile.profile_photo", read_only=True)
    role = serializers.CharField(source="profile.role", read_only=True)
    is_verified_author = serializers.BooleanField(source="profile.is_verified_author", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "profile_photo",
            "role",
            "is_verified_author",
        )


class NewsCommentSerializer(serializers.ModelSerializer):
    user = NewsAuthorSerializer(read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = NewsComment
        fields = ("id", "news", "user", "parent", "content", "created_at", "updated_at", "replies")
        read_only_fields = ("news", "user", "created_at", "updated_at")

    def validate(self, attrs):
        content = attrs.get("content", "").strip()
        from apps.moderation.validators import validate_moderated_content, is_user_muted
        request = self.context.get("request")
        user = request.user if request else None
        if user and not user.is_anonymous:
            news = attrs.get("news") or self.context.get("news")
            community = news.community if news else None
            if is_user_muted(user, community=community):
                raise serializers.ValidationError("You are currently muted and cannot post comments.")
        if content:
            validate_moderated_content(content, user=user)
        return attrs

    def get_replies(self, obj: NewsComment) -> list[dict]:
        # Return nested child comments
        replies = obj.replies.all()
        return NewsCommentSerializer(replies, many=True, context=self.context).data


class NewsSerializer(serializers.ModelSerializer):
    author = NewsAuthorSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    attachments = NewsAttachmentSerializer(many=True, read_only=True)
    likes_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()
    community_name = serializers.CharField(source="community.name", read_only=True)
    community_slug = serializers.CharField(source="community.slug", read_only=True)

    class Meta:
        model = News
        fields = (
            "id",
            "title",
            "content",
            "category",
            "scope",
            "community",
            "community_name",
            "community_slug",
            "college",
            "author",
            "status",
            "scheduled_publish_at",
            "is_pinned",
            "is_featured",
            "is_blocked",
            "image",
            "banner",
            "views_count",
            "shares_count",
            "likes_count",
            "comments_count",
            "is_liked",
            "is_bookmarked",
            "tags",
            "attachments",
            "created_at",
            "updated_at",
        )

    def get_likes_count(self, obj: News) -> int:
        if hasattr(obj, "likes_count_annotated"):
            return obj.likes_count_annotated
        return obj.likes.count()

    def get_comments_count(self, obj: News) -> int:
        if hasattr(obj, "comments_count_annotated"):
            return obj.comments_count_annotated
        return obj.comments.count()

    def get_is_liked(self, obj: News) -> bool:
        request = self.context.get("request")
        if not request or not request.user or request.user.is_anonymous:
            return False
        return obj.likes.filter(user=request.user).exists()

    def get_is_bookmarked(self, obj: News) -> bool:
        request = self.context.get("request")
        if not request or not request.user or request.user.is_anonymous:
            return False
        return obj.bookmarks.filter(user=request.user).exists()


class NewsCreateUpdateSerializer(serializers.ModelSerializer):
    tags = serializers.ListField(child=serializers.CharField(), required=False)

    class Meta:
        model = News
        fields = (
            "id",
            "title",
            "content",
            "category",
            "scope",
            "community",
            "college",
            "status",
            "scheduled_publish_at",
            "is_pinned",
            "is_featured",
            "image",
            "banner",
            "tags",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate(self, attrs):
        scope = attrs.get("scope", getattr(self.instance, "scope", News.Scope.PLATFORM))
        community = attrs.get("community", getattr(self.instance, "community", None))
        college = attrs.get("college", getattr(self.instance, "college", None))

        if scope == News.Scope.COMMUNITY and not community:
            raise serializers.ValidationError({"community": "Community is required for community scope."})
        if scope == News.Scope.COLLEGE and not college:
            raise serializers.ValidationError({"college": "College is required for college scope."})

        # Moderation checks
        content = attrs.get("content", "").strip()
        title = attrs.get("title", "").strip()
        from apps.moderation.validators import validate_moderated_content, is_user_muted
        request = self.context.get("request")
        user = request.user if request else None
        if user and not user.is_anonymous:
            if is_user_muted(user, community=community):
                raise serializers.ValidationError("You are currently muted and cannot post news.")
        if content:
            validate_moderated_content(content, user=user)
        if title:
            validate_moderated_content(title, user=user)

        return attrs

    def create(self, validated_data) -> News:
        tags_data = validated_data.pop("tags", [])
        news = News.objects.create(**validated_data)
        for tag_name in tags_data:
            tag, _ = Tag.objects.get_or_create(name=tag_name.strip().lower())
            news.tags.add(tag)
        return news

    def update(self, instance: News, validated_data) -> News:
        tags_data = validated_data.pop("tags", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if tags_data is not None:
            instance.tags.clear()
            for tag_name in tags_data:
                tag, _ = Tag.objects.get_or_create(name=tag_name.strip().lower())
                instance.tags.add(tag)
        return instance

    def to_representation(self, instance: News) -> dict:
        return NewsSerializer(instance, context=self.context).data


class NewsReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsReport
        fields = ("id", "news", "user", "reason", "created_at")
        read_only_fields = ("news", "user", "created_at")
