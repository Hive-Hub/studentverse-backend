from django.contrib import admin
from apps.messaging.models import Message, MessageAttachment, MessageReaction


class MessageAttachmentInline(admin.TabularInline):
    model = MessageAttachment
    extra = 0
    readonly_fields = ("file_name", "file_size", "mime_type", "uploaded_at")


class MessageReactionInline(admin.TabularInline):
    model = MessageReaction
    extra = 0
    readonly_fields = ("user", "emoji", "created_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "channel", "content_preview", "is_pinned", "is_edited", "created_at")
    list_filter = ("is_pinned", "is_edited", "channel__community")
    search_fields = ("content", "author__username", "channel__name")
    readonly_fields = ("is_edited", "edited_at", "created_at", "updated_at")
    inlines = [MessageAttachmentInline, MessageReactionInline]

    def content_preview(self, obj):
        return obj.content[:60] + "..." if len(obj.content) > 60 else obj.content
    content_preview.short_description = "Content"


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "file_name", "mime_type", "file_size", "message", "uploaded_at")
    search_fields = ("file_name", "message__author__username")


@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "emoji", "message", "created_at")
    list_filter = ("emoji",)
    search_fields = ("user__username", "emoji")
