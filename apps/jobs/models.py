import uuid
from django.db import models
from apps.channels.models import Video


class Job(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    class Stage(models.TextChoices):
        FETCH = "fetch", "Fetch"
        DOWNLOAD = "download", "Download"
        TRANSCRIBE = "transcribe", "Transcribe"
        UPLOAD = "upload", "Upload"
        CATEGORIZE = "categorize", "Categorize"
        SUMMARIZE = "summarize", "Summarize"
        EMBED = "embed", "Embed"
        UPSERT = "upsert", "Upsert"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="jobs")
    pipeline_version = models.CharField(max_length=20, default="1")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True
    )
    stage = models.CharField(
        max_length=20, choices=Stage.choices, default=Stage.FETCH
    )
    progress = models.IntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Job({self.video_id}, {self.stage}, {self.status})"

    @property
    def duration_sec(self):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class Artifact(models.Model):
    class ArtifactType(models.TextChoices):
        TRANSCRIPT_JSON = "transcript_json", "Transcript JSON"
        TRANSCRIPT_TXT = "transcript_txt", "Transcript TXT"
        SUMMARY_MD = "summary_md", "Summary MD"
        AUDIO_WAV = "audio_wav", "Audio WAV"
        AUDIO_M4A = "audio_m4a", "Audio M4A"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="artifacts")
    type = models.CharField(max_length=30, choices=ArtifactType.choices)
    local_path = models.TextField(blank=True)
    gcs_uri = models.TextField(blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Artifact({self.type}, {self.video_id})"


class VectorIndexItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="vector_items")
    pinecone_namespace = models.CharField(max_length=200)
    pinecone_vector_id = models.CharField(max_length=200, unique=True)
    embedding_model = models.CharField(max_length=100)
    chunking_version = models.CharField(max_length=20, default="v1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"VectorItem({self.pinecone_vector_id})"
