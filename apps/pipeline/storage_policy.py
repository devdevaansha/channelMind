import logging
import pathlib
import shutil

import django.utils.timezone as tz
from django.conf import settings

from apps.channels.models import Video
from apps.jobs.models import Artifact, Job

logger = logging.getLogger(__name__)


def _retention_mode() -> str:
    return str(getattr(settings, "VIDEO_RETENTION_MODE", "delete_all")).strip().lower()


def cleanup_video_local_data(video_id: str, channel_id: str, keep_transcript: bool = False) -> None:
    """
    Delete all local per-video working files to save disk space.

    This removes:
      /data/channels/<channel_id>/videos/<video_id>/
    """
    video_dir = (
        pathlib.Path(settings.DATA_DIR)
        / "channels"
        / str(channel_id)
        / "videos"
        / str(video_id)
    )
    transcript_json = video_dir / "transcript" / "transcript.json"
    transcript_txt = video_dir / "transcript" / "transcript.txt"
    keep_transcript_files = keep_transcript and (
        transcript_json.exists() or transcript_txt.exists()
    )

    if video_dir.exists():
        if keep_transcript_files:
            for child in list(video_dir.iterdir()):
                if child.name == "transcript":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            logger.info("Deleted non-transcript local files for video dir: %s", video_dir)
        else:
            shutil.rmtree(video_dir)
            logger.info("Deleted local video dir: %s", video_dir)

    # Refresh DB pointers so they reflect retained files accurately.
    transcript_local_path = ""
    if keep_transcript_files:
        if transcript_json.exists():
            transcript_local_path = str(transcript_json)
        elif transcript_txt.exists():
            transcript_local_path = str(transcript_txt)

    Video.objects.filter(pk=video_id).update(
        transcript_local_path=transcript_local_path,
        summary_local_path="",
        updated_at=tz.now(),
    )

    if keep_transcript_files:
        Artifact.objects.filter(
            video_id=video_id,
            type__in=[
                Artifact.ArtifactType.SUMMARY_MD,
                Artifact.ArtifactType.AUDIO_WAV,
                Artifact.ArtifactType.AUDIO_M4A,
            ],
        ).update(local_path="", sha256="")
    else:
        Artifact.objects.filter(video_id=video_id).update(local_path="", sha256="")


def finalize_failed_job(job_id: str, video_id: str, channel_id: str, error: Exception) -> None:
    """Mark job/video failed and delete local files."""
    now = tz.now()
    Job.objects.filter(pk=job_id).update(
        status=Job.Status.FAILED,
        error=str(error),
        finished_at=now,
        updated_at=now,
    )
    Video.objects.filter(pk=video_id).update(
        status=Video.Status.FAILED,
        updated_at=now,
    )
    keep_transcript = _retention_mode() == "keep_transcript_on_failure"
    cleanup_video_local_data(video_id, channel_id, keep_transcript=keep_transcript)


def finalize_succeeded_job(job_id: str, video_id: str, channel_id: str) -> None:
    """Mark job/video succeeded and delete local files."""
    now = tz.now()
    Job.objects.filter(pk=job_id).update(
        status=Job.Status.SUCCEEDED,
        progress=100,
        finished_at=now,
        updated_at=now,
    )
    Video.objects.filter(pk=video_id).update(
        status=Video.Status.DONE,
        updated_at=now,
    )
    cleanup_video_local_data(video_id, channel_id)
