import logging
import pathlib

import django.utils.timezone as tz
from celery import shared_task
from django.conf import settings

from apps.channels.models import Category, Video
from apps.jobs.models import Job
from apps.pipeline.progress import update_job_progress

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="pipeline",
    name="pipeline.auto_categorize",
)
def auto_categorize(self, job_id: str, video_id: str) -> None:
    """
    Stage E: Auto-assign category via Gemini if no manual category is set.
    If the channel has a default_category, use that directly.
    """
    logger.info("auto_categorize start job=%s video=%s", job_id, video_id)

    try:
        video = Video.objects.select_related("channel__default_category").get(pk=video_id)
    except Video.DoesNotExist:
        return

    Job.objects.filter(pk=job_id).update(stage=Job.Stage.CATEGORIZE, updated_at=tz.now())
    update_job_progress(job_id, "categorize", 0.0)

    # If already categorised (manual), skip
    if video.category_id:
        logger.info("Video %s already has category; skipping auto-categorize", video_id)
        update_job_progress(job_id, "categorize", 1.0)
        return

    # Use channel default category if set
    if video.channel.default_category_id:
        Video.objects.filter(pk=video_id).update(
            category_id=video.channel.default_category_id,
            updated_at=tz.now(),
        )
        update_job_progress(job_id, "categorize", 1.0)
        return

    # Auto-classify with Gemini
    categories = list(Category.objects.values_list("name", flat=True))
    if not categories:
        logger.info("No categories configured; skipping auto-categorize")
        update_job_progress(job_id, "categorize", 1.0)
        return

    if not video.transcript_local_path:
        update_job_progress(job_id, "categorize", 1.0)
        return

    transcript_path = pathlib.Path(video.transcript_local_path)
    if not transcript_path.exists():
        update_job_progress(job_id, "categorize", 1.0)
        return

    # Read plain text transcript for classification
    txt_path = transcript_path.parent / "transcript.txt"
    transcript_text = txt_path.read_text(encoding="utf-8") if txt_path.exists() else ""

    try:
        from services.gemini_client import GeminiClient
        client = GeminiClient()
        category_name, confidence = client.classify_category(transcript_text, categories)
    except Exception as exc:
        logger.warning("auto_categorize Gemini call failed: %s (continuing)", exc)
        update_job_progress(job_id, "categorize", 1.0)
        return

    try:
        category = Category.objects.get(name=category_name)
        Video.objects.filter(pk=video_id).update(
            category=category,
            auto_category_confidence=confidence,
            updated_at=tz.now(),
        )
        logger.info("Auto-categorized video=%s as '%s' (confidence=%.2f)", video_id, category_name, confidence)
    except Category.DoesNotExist:
        logger.warning("Gemini returned unknown category '%s'; skipping", category_name)

    update_job_progress(job_id, "categorize", 1.0)
