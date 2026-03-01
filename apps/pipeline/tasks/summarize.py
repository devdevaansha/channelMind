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
from services.gemini_client import GeminiClient
from services.gcs_client import get_gcs_client

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=600,
    queue="pipeline",
    name="pipeline.summarize_video",
)
def summarize_video(self, job_id: str, video_id: str) -> None:
    """Stage F: Summarize transcript with Gemini (only runs if summarize_enabled)."""
    logger.info("summarize_video start job=%s video=%s", job_id, video_id)

    try:
        video = Video.objects.select_related("channel").get(pk=video_id)
    except Video.DoesNotExist:
        return

    Job.objects.filter(pk=job_id).update(stage=Job.Stage.SUMMARIZE, updated_at=tz.now())
    update_job_progress(job_id, "summarize", 0.0)

    if not video.transcript_local_path:
        logger.warning("No transcript for video=%s; skipping summary", video_id)
        update_job_progress(job_id, "summarize", 1.0)
        return

    txt_path = pathlib.Path(video.transcript_local_path).parent / "transcript.txt"
    if not txt_path.exists():
        update_job_progress(job_id, "summarize", 1.0)
        return

    transcript_text = txt_path.read_text(encoding="utf-8")

    try:
        client = GeminiClient()
        summary_md = client.summarize(transcript_text, video.title)
    except Exception as exc:
        logger.exception("summarize_video Gemini failed job=%s: %s", job_id, exc)
        if self.request.retries >= self.max_retries:
            finalize_failed_job(job_id, video_id, str(video.channel_id), exc)
            raise
        raise self.retry(exc=exc)

    update_job_progress(job_id, "summarize", 0.7)

    # Save locally
    channel_id = str(video.channel_id)
    base_dir = (
        pathlib.Path(settings.DATA_DIR)
        / "channels" / channel_id
        / "videos" / str(video_id)
    )
    summary_dir = base_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    md_path = summary_dir / "summary.md"
    json_path = summary_dir / "summary.json"
    md_path.write_text(summary_md, encoding="utf-8")
    json_path.write_text(
        json.dumps({"video_id": str(video_id), "summary": summary_md}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    Video.objects.filter(pk=video_id).update(
        summary_local_path=str(md_path), updated_at=tz.now()
    )

    Artifact.objects.get_or_create(
        video_id=video_id,
        type=Artifact.ArtifactType.SUMMARY_MD,
        defaults={"local_path": str(md_path)},
    )

    # Upload to GCS
    try:
        gcs = get_gcs_client()
        gcs_prefix = video.gcs_prefix or f"youtube/channels/{channel_id}/videos/{video_id}"
        gcs.upload_file(md_path, f"{gcs_prefix}/summary/summary.md")
        gcs.upload_file(json_path, f"{gcs_prefix}/summary/summary.json")
    except Exception as exc:
        logger.warning("GCS upload of summary failed (non-fatal): %s", exc)

    update_job_progress(job_id, "summarize", 1.0)
    logger.info("summarize_video done job=%s", job_id)
