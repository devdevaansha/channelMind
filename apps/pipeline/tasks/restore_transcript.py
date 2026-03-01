import logging
import pathlib

import django.utils.timezone as tz
from celery import shared_task
from django.conf import settings

from apps.channels.models import Video
from apps.jobs.models import Job
from apps.pipeline.progress import update_job_progress
from services.gcs_client import get_gcs_client

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=300,
    queue="pipeline",
    name="pipeline.restore_transcript",
)
def restore_transcript(self, job_id: str, video_id: str) -> None:
    """
    Download transcript.json and transcript.txt from GCS so that
    downstream tasks (summarize, embed, upsert) can operate on local files.

    Used when re-processing DONE videos whose local data was cleaned up.
    """
    logger.info("restore_transcript start job=%s video=%s", job_id, video_id)

    try:
        video = Video.objects.select_related("channel").get(pk=video_id)
    except Video.DoesNotExist:
        return

    Job.objects.filter(pk=job_id).update(stage=Job.Stage.FETCH, updated_at=tz.now())
    update_job_progress(job_id, "fetch", 0.0)

    if video.transcript_local_path:
        local = pathlib.Path(video.transcript_local_path)
        if local.exists():
            logger.info("Transcript already exists locally for video=%s", video_id)
            update_job_progress(job_id, "fetch", 1.0)
            return

    gcs_prefix = video.gcs_prefix
    if not gcs_prefix:
        logger.warning("No gcs_prefix for video=%s; cannot restore transcript", video_id)
        update_job_progress(job_id, "fetch", 1.0)
        return

    channel_id = str(video.channel_id)
    transcript_dir = (
        pathlib.Path(settings.DATA_DIR)
        / "channels" / channel_id
        / "videos" / str(video_id)
        / "transcript"
    )
    transcript_dir.mkdir(parents=True, exist_ok=True)

    gcs = get_gcs_client()
    json_path = transcript_dir / "transcript.json"
    txt_path = transcript_dir / "transcript.txt"

    try:
        json_content = gcs.download_as_text(f"{gcs_prefix}/transcript/transcript.json")
        json_path.write_text(json_content, encoding="utf-8")
        update_job_progress(job_id, "fetch", 0.5)
    except Exception as exc:
        logger.exception("Failed to download transcript.json from GCS: %s", exc)
        if self.request.retries >= self.max_retries:
            raise
        raise self.retry(exc=exc)

    try:
        txt_content = gcs.download_as_text(f"{gcs_prefix}/transcript/transcript.txt")
        txt_path.write_text(txt_content, encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to download transcript.txt from GCS (non-fatal): %s", exc)

    Video.objects.filter(pk=video_id).update(
        transcript_local_path=str(json_path),
        updated_at=tz.now(),
    )

    update_job_progress(job_id, "fetch", 1.0)
    logger.info("restore_transcript done job=%s video=%s", job_id, video_id)
