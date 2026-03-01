"""Finish task for minimal pipeline (download → transcribe → summarize)."""
import logging

from celery import shared_task
from apps.channels.models import Video
from apps.pipeline.storage_policy import finalize_succeeded_job

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    queue="pipeline",
    name="pipeline.finish_minimal_pipeline",
)
def finish_minimal_pipeline(self, job_id: str, video_id: str) -> None:
    """Mark job succeeded and video done after minimal pipeline."""
    logger.info("finish_minimal_pipeline job=%s video=%s", job_id, video_id)
    channel_id = Video.objects.values_list("channel_id", flat=True).get(pk=video_id)
    finalize_succeeded_job(job_id, video_id, str(channel_id))
    logger.info("finish_minimal_pipeline done job=%s", job_id)
