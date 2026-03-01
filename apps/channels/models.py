import uuid
from django.db import models


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    created_by = models.CharField(max_length=100, default="system")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Channel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    youtube_channel_id = models.TextField(unique=True)
    title = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    sync_cursor = models.TextField(blank=True, default="")
    summarize_enabled = models.BooleanField(default=False)
    default_category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="channels"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or self.youtube_channel_id


class Video(models.Model):
    class Status(models.TextChoices):
        DISCOVERED = "discovered", "Discovered"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="videos")
    youtube_video_id = models.TextField(unique=True)
    title = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    duration_sec = models.IntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DISCOVERED, db_index=True
    )
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="videos"
    )
    auto_category_confidence = models.FloatField(null=True, blank=True)
    transcript_local_path = models.TextField(blank=True)
    summary_local_path = models.TextField(blank=True)
    gcs_prefix = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title or self.youtube_video_id

    @property
    def youtube_url(self):
        return f"https://www.youtube.com/watch?v={self.youtube_video_id}"
