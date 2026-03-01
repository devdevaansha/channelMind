from django.contrib import admin
from .models import Category, Channel, Video


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    search_fields = ["name"]


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ["title", "youtube_channel_id", "summarize_enabled", "last_synced_at", "created_at"]
    list_filter = ["summarize_enabled"]
    search_fields = ["title", "youtube_channel_id"]
    readonly_fields = ["id", "created_at", "last_synced_at"]


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ["title", "channel", "status", "category", "published_at", "created_at"]
    list_filter = ["status", "channel", "category"]
    search_fields = ["title", "youtube_video_id"]
    readonly_fields = ["id", "created_at", "updated_at"]
