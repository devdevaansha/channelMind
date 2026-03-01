import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200, unique=True)),
                ("created_by", models.CharField(default="system", max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name_plural": "categories", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Channel",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("youtube_channel_id", models.TextField(unique=True)),
                ("title", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("sync_cursor", models.TextField(blank=True, default="")),
                ("summarize_enabled", models.BooleanField(default=False)),
                ("default_category", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="channels", to="channels.category"
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Video",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("youtube_video_id", models.TextField(unique=True)),
                ("title", models.TextField(blank=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("duration_sec", models.IntegerField(blank=True, null=True)),
                ("status", models.CharField(
                    choices=[
                        ("discovered", "Discovered"), ("queued", "Queued"),
                        ("processing", "Processing"), ("done", "Done"), ("failed", "Failed"),
                    ],
                    db_index=True, default="discovered", max_length=20,
                )),
                ("auto_category_confidence", models.FloatField(blank=True, null=True)),
                ("transcript_local_path", models.TextField(blank=True)),
                ("summary_local_path", models.TextField(blank=True)),
                ("gcs_prefix", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("channel", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="videos", to="channels.channel",
                )),
                ("category", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="videos", to="channels.category",
                )),
            ],
            options={"ordering": ["-published_at"]},
        ),
    ]
