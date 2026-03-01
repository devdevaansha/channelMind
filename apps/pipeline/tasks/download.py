import logging
import pathlib

import django.utils.timezone as tz
from celery import shared_task
from django.conf import settings

from apps.channels.models import Video
from apps.jobs.models import Job
from apps.pipeline.progress import update_job_progress
from apps.pipeline.storage_policy import finalize_failed_job

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="pipeline",
    name="pipeline.download_audio",
)
def download_audio(self, job_id: str, video_id: str) -> None:
    """Stage B: Download audio via yt-dlp."""
    logger.info("download_audio start job=%s video=%s", job_id, video_id)

    try:
        video = Video.objects.select_related("channel").get(pk=video_id)
    except Video.DoesNotExist:
        logger.error("Video not found: %s", video_id)
        return

    Job.objects.filter(pk=job_id).update(
        status=Job.Status.RUNNING,
        stage=Job.Stage.DOWNLOAD,
        started_at=tz.now(),
        updated_at=tz.now(),
    )
    Video.objects.filter(pk=video_id).update(status=Video.Status.PROCESSING)
    update_job_progress(job_id, "download", 0.0)

    out_dir = (
        pathlib.Path(settings.DATA_DIR)
        / "channels" / str(video.channel_id)
        / "videos" / str(video_id)
        / "source"
    )

    def progress_hook(d: dict) -> None:
        if d.get("status") == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            pct = min(downloaded / total, 0.99)
            update_job_progress(job_id, "download", pct)

    from services.ytdlp_client import YtDlpClient

    try:
        client = YtDlpClient()
        client.download(
            video_id=video.youtube_video_id,
            output_dir=out_dir,
            progress_hook=progress_hook,
        )
    except Exception as exc:
        logger.exception("download_audio failed job=%s: %s", job_id, exc)
        if self.request.retries >= self.max_retries:
            finalize_failed_job(job_id, video_id, str(video.channel_id), exc)
            raise
        raise self.retry(exc=exc)

    update_job_progress(job_id, "download", 1.0)
    logger.info("download_audio done job=%s", job_id)
