import json
import logging
import pathlib

import django.utils.timezone as tz
from celery import shared_task
from django.conf import settings

from apps.channels.models import Video
from apps.jobs.models import Artifact, Job
from apps.pipeline.progress import update_job_progress
from apps.pipeline.storage_policy import finalize_failed_job
from services.gcs_client import get_gcs_client

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="pipeline",
    name="pipeline.upload_artifacts",
)
def upload_artifacts(self, job_id: str, video_id: str) -> None:
    """Stage D: Upload transcript artifacts to GCS with organized prefix layout."""
    logger.info("upload_artifacts start job=%s video=%s", job_id, video_id)

    try:
        video = Video.objects.select_related("channel").get(pk=video_id)
    except Video.DoesNotExist:
        return

    Job.objects.filter(pk=job_id).update(stage=Job.Stage.UPLOAD, updated_at=tz.now())
    update_job_progress(job_id, "upload", 0.0)

    channel_id = str(video.channel_id)
    gcs_prefix = f"youtube/channels/{channel_id}/videos/{video_id}"

    try:
        gcs = get_gcs_client()

        # Upload channel metadata (idempotent)
        channel_meta_path = f"youtube/channels/{channel_id}/channel.json"
        if not gcs.exists(channel_meta_path):
            gcs.upload_json(
                {"channel_id": channel_id, "title": video.channel.title},
                channel_meta_path,
            )

        # Upload video metadata
        video_meta = {
            "video_id": str(video.id),
            "youtube_video_id": video.youtube_video_id,
            "title": video.title,
            "published_at": video.published_at.isoformat() if video.published_at else None,
            "duration_sec": video.duration_sec,
        }
        gcs.upload_json(video_meta, f"{gcs_prefix}/metadata.json")
        update_job_progress(job_id, "upload", 0.2)

        base_dir = (
            pathlib.Path(settings.DATA_DIR)
            / "channels" / channel_id
            / "videos" / str(video_id)
        )

        # Upload transcript files
        artifacts_to_upload = [
            (base_dir / "transcript" / "transcript.json", f"{gcs_prefix}/transcript/transcript.json", Artifact.ArtifactType.TRANSCRIPT_JSON),
            (base_dir / "transcript" / "transcript.txt", f"{gcs_prefix}/transcript/transcript.txt", Artifact.ArtifactType.TRANSCRIPT_TXT),
        ]

        for i, (local_path, gcs_path, artifact_type) in enumerate(artifacts_to_upload):
            if local_path.exists():
                sha = gcs.sha256_of_file(local_path)
                uri = gcs.upload_file(local_path, gcs_path)
                Artifact.objects.filter(video_id=video_id, type=artifact_type).update(
                    gcs_uri=uri, sha256=sha
                )
            update_job_progress(job_id, "upload", 0.3 + 0.3 * i)

        # Upload summary if it exists
        summary_dir = base_dir / "summary"
        for fname in ["summary.md", "summary.json"]:
            fpath = summary_dir / fname
            if fpath.exists():
                gcs.upload_file(fpath, f"{gcs_prefix}/summary/{fname}")

        update_job_progress(job_id, "upload", 0.9)

    except Exception as exc:
        logger.exception("upload_artifacts failed job=%s: %s", job_id, exc)
        if self.request.retries >= self.max_retries:
            finalize_failed_job(job_id, video_id, channel_id, exc)
            raise
        raise self.retry(exc=exc)

    Video.objects.filter(pk=video_id).update(
        gcs_prefix=gcs_prefix, updated_at=tz.now()
    )
    update_job_progress(job_id, "upload", 1.0)
    logger.info("upload_artifacts done job=%s prefix=%s", job_id, gcs_prefix)
