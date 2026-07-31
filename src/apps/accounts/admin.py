from __future__ import annotations

from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "firebase_uid", "display_name", "role", "updated_at")
    list_filter = ("role", "updated_at")
    search_fields = ("user__username", "user__email", "firebase_uid", "display_name")
    readonly_fields = ("created_at", "updated_at")
