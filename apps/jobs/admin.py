from django.contrib import admin
from .models import Job, Artifact, VectorIndexItem


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["video", "stage", "status", "progress", "created_at", "finished_at"]
    list_filter = ["status", "stage"]
    search_fields = ["video__title"]
    readonly_fields = ["id", "created_at", "updated_at", "started_at", "finished_at"]


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    list_display = ["video", "type", "gcs_uri", "created_at"]
    list_filter = ["type"]
    search_fields = ["video__title"]
    readonly_fields = ["id", "created_at"]


@admin.register(VectorIndexItem)
class VectorIndexItemAdmin(admin.ModelAdmin):
    list_display = ["video", "pinecone_vector_id", "embedding_model", "created_at"]
    search_fields = ["pinecone_vector_id", "video__title"]
    readonly_fields = ["id", "created_at"]
