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

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=7200,   # 2 hour hard limit for very long videos
    soft_time_limit=6900,
    queue="pipeline",
    name="pipeline.transcribe_audio",
)
def transcribe_audio(self, job_id: str, video_id: str) -> None:
    """Stage C: Transcribe audio with faster-whisper (GPU)."""
    logger.info("transcribe_audio start job=%s video=%s", job_id, video_id)

    try:
        video = Video.objects.select_related("channel").get(pk=video_id)
    except Video.DoesNotExist:
        logger.error("Video not found: %s", video_id)
        return

    Job.objects.filter(pk=job_id).update(
        stage=Job.Stage.TRANSCRIBE,
        updated_at=tz.now(),
    )
    update_job_progress(job_id, "transcribe", 0.0)

    base_dir = (
        pathlib.Path(settings.DATA_DIR)
        / "channels" / str(video.channel_id)
        / "videos" / str(video_id)
    )
    source_dir = base_dir / "source"
    transcript_dir = base_dir / "transcript"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    # Find downloaded audio
    audio_candidates = list(source_dir.glob("audio.*"))
    if not audio_candidates:
        exc = FileNotFoundError(f"No audio file in {source_dir}")
        if self.request.retries >= self.max_retries:
            finalize_failed_job(job_id, video_id, str(video.channel_id), exc)
            raise
        raise self.retry(exc=exc)

    audio_path = audio_candidates[0]

    from services.whisper_client import WhisperClient

    try:
        client = WhisperClient(
            model_size=settings.WHISPER_MODEL,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
            beam_size=settings.WHISPER_BEAM_SIZE,
        )
        result = client.transcribe(
            audio_path=audio_path,
            progress_callback=lambda p: update_job_progress(job_id, "transcribe", p),
        )
    except Exception as exc:
        logger.exception("transcribe_audio failed job=%s: %s", job_id, exc)
        if self.request.retries >= self.max_retries:
            finalize_failed_job(job_id, video_id, str(video.channel_id), exc)
            raise
        raise self.retry(exc=exc)

    json_path = transcript_dir / "transcript.json"
    txt_path = transcript_dir / "transcript.txt"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(result["text"], encoding="utf-8")

    Video.objects.filter(pk=video_id).update(
        transcript_local_path=str(json_path),
        updated_at=tz.now(),
    )

    Artifact.objects.get_or_create(
        video_id=video_id,
        type=Artifact.ArtifactType.TRANSCRIPT_JSON,
        defaults={"local_path": str(json_path)},
    )
    Artifact.objects.get_or_create(
        video_id=video_id,
        type=Artifact.ArtifactType.TRANSCRIPT_TXT,
        defaults={"local_path": str(txt_path)},
    )

    update_job_progress(job_id, "transcribe", 1.0)
    logger.info("transcribe_audio done job=%s segments=%d", job_id, len(result["segments"]))
