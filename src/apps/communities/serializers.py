from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers
from apps.communities.models import Community, CommunityMember, Channel
from apps.communities.validators import (
    validate_community_name,
    validate_image_file,
    validate_channel_name,
)

User = get_user_model()



class UserMiniSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source="profile.display_name", read_only=True)
    profile_photo = serializers.ImageField(source="profile.profile_photo", read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "display_name", "profile_photo")


class CommunitySerializer(serializers.ModelSerializer):
    members_count = serializers.IntegerField(read_only=True)
    admins_count = serializers.IntegerField(read_only=True)
    moderators_count = serializers.IntegerField(read_only=True)
    is_member = serializers.SerializerMethodField()
    user_role = serializers.SerializerMethodField()

    class Meta:
        model = Community
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "banner",
            "icon",
            "invite_code",
            "is_public",
            "rules",
            "created_at",
            "updated_at",
            "members_count",
            "admins_count",
            "moderators_count",
            "is_member",
            "user_role",
        )
        read_only_fields = ("slug", "invite_code", "created_at", "updated_at")

    def get_is_member(self, obj: Community) -> bool:
        request = self.context.get("request")
        if not request or not request.user or request.user.is_anonymous:
            return False
        return obj.memberships.filter(user=request.user).exists()

    def get_user_role(self, obj: Community) -> str | None:
        request = self.context.get("request")
        if not request or not request.user or request.user.is_anonymous:
            return None
        membership = obj.memberships.filter(user=request.user).first()
        return membership.role if membership else None


class CommunityCreateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(validators=[validate_community_name])
    banner = serializers.ImageField(validators=[validate_image_file], required=False, allow_null=True)
    icon = serializers.ImageField(validators=[validate_image_file], required=False, allow_null=True)

    class Meta:
        model = Community
        fields = ("id", "name", "description", "banner", "icon", "is_public", "rules", "slug", "invite_code")
        read_only_fields = ("slug", "invite_code")


class CommunityMemberSerializer(serializers.ModelSerializer):
    user = UserMiniSerializer(read_only=True)

    class Meta:
        model = CommunityMember
        fields = ("id", "user", "role", "joined_at")


class CommunityMemberRoleUpdateSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(
        choices=[
            (CommunityMember.Role.ADMIN, "Admin"),
            (CommunityMember.Role.MODERATOR, "Moderator"),
            (CommunityMember.Role.MEMBER, "Member"),
        ]
    )

    class Meta:
        model = CommunityMember
        fields = ("role",)


class ChannelSerializer(serializers.ModelSerializer):
    can_write = serializers.SerializerMethodField()

    class Meta:
        model = Channel
        fields = (
            "id",
            "community",
            "name",
            "slug",
            "description",
            "channel_type",
            "permission_type",
            "is_pinned",
            "is_archived",
            "order",
            "created_at",
            "updated_at",
            "can_write",
        )
        read_only_fields = ("slug", "created_at", "updated_at")

    def get_can_write(self, obj: Channel) -> bool:
        request = self.context.get("request")
        if not request or not request.user or request.user.is_anonymous:
            return False

        community = obj.community
        # Check parent community membership
        membership = community.memberships.filter(user=request.user).first()
        if not membership:
            return False

        # Enforce write checks based on permission_type
        if obj.permission_type == Channel.PermissionType.WRITE:
            return True
        
        # For 'read_only' and 'moderator_only': only owner, admin, and moderator can write
        return membership.role in [
            CommunityMember.Role.OWNER,
            CommunityMember.Role.ADMIN,
            CommunityMember.Role.MODERATOR,
        ]


class ChannelCreateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(validators=[validate_channel_name])
    community = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Community.objects.all(),
        help_text="Slug of the community to create the channel in."
    )

    class Meta:
        model = Channel
        fields = (
            "id",
            "community",
            "name",
            "description",
            "channel_type",
            "permission_type",
            "is_pinned",
            "is_archived",
            "order",
            "slug",
        )
        read_only_fields = ("slug",)

    def validate(self, data):
        community = data["community"]
        name = data["name"]
        
        # Slugified name must be unique within the community
        from django.utils.text import slugify
        name_slug = slugify(name.lower())
        if Channel.objects.filter(community=community, slug=name_slug).exists():
            raise serializers.ValidationError(
                {"name": "A channel with this name (or slugified name) already exists in this community."}
            )
        return data


class ChannelUpdateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(validators=[validate_channel_name], required=False)

    class Meta:
        model = Channel
        fields = (
            "name",
            "description",
            "channel_type",
            "permission_type",
            "is_pinned",
            "is_archived",
            "order",
        )

    def validate(self, data):
        name = data.get("name")
        if name:
            community = self.instance.community
            from django.utils.text import slugify
            name_slug = slugify(name.lower())
            # Check unique if renaming to a different name
            if name_slug != self.instance.slug:
                if Channel.objects.filter(community=community, slug=name_slug).exists():
                    raise serializers.ValidationError(
                        {"name": "A channel with this name (or slugified name) already exists in this community."}
                    )
        return data

