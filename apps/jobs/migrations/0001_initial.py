import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("channels", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Job",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("pipeline_version", models.CharField(default="1", max_length=20)),
                ("status", models.CharField(
                    choices=[
                        ("queued", "Queued"), ("running", "Running"),
                        ("succeeded", "Succeeded"), ("failed", "Failed"), ("canceled", "Canceled"),
                    ],
                    db_index=True, default="queued", max_length=20,
                )),
                ("stage", models.CharField(
                    choices=[
                        ("fetch", "Fetch"), ("download", "Download"), ("transcribe", "Transcribe"),
                        ("upload", "Upload"), ("categorize", "Categorize"), ("summarize", "Summarize"),
                        ("embed", "Embed"), ("upsert", "Upsert"),
                    ],
                    default="fetch", max_length=20,
                )),
                ("progress", models.IntegerField(default=0)),
                ("error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("video", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="jobs", to="channels.video",
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Artifact",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("type", models.CharField(
                    choices=[
                        ("transcript_json", "Transcript JSON"), ("transcript_txt", "Transcript TXT"),
                        ("summary_md", "Summary MD"), ("audio_wav", "Audio WAV"), ("audio_m4a", "Audio M4A"),
                    ],
                    max_length=30,
                )),
                ("local_path", models.TextField(blank=True)),
                ("gcs_uri", models.TextField(blank=True)),
                ("sha256", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("video", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="artifacts", to="channels.video",
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="VectorIndexItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("pinecone_namespace", models.CharField(max_length=200)),
                ("pinecone_vector_id", models.CharField(max_length=200, unique=True)),
                ("embedding_model", models.CharField(max_length=100)),
                ("chunking_version", models.CharField(default="v1", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("video", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="vector_items", to="channels.video",
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
