import json
import logging
import pathlib

from django.conf import settings

logger = logging.getLogger(__name__)


def load_transcript(video):
    """Load transcript JSON from local path, falling back to GCS."""
    if video.transcript_local_path:
        tp = pathlib.Path(video.transcript_local_path)
        if tp.exists():
            try:
                return json.loads(tp.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("Failed to read local transcript for video=%s", video.pk)

    if video.gcs_prefix and settings.GCS_BUCKET:
        gcs_path = f"{video.gcs_prefix}/transcript/transcript.json"
        try:
            from services.gcs_client import get_gcs_client
            gcs = get_gcs_client()
            text = gcs.download_as_text(gcs_path)
            if text:
                return json.loads(text)
        except Exception:
            logger.warning("Failed to read GCS transcript for video=%s at %s", video.pk, gcs_path)

    return None


def load_summary(video):
    """Load summary text from local path, falling back to GCS."""
    if video.summary_local_path:
        sp = pathlib.Path(video.summary_local_path)
        if sp.exists():
            try:
                return sp.read_text(encoding="utf-8")
            except Exception:
                logger.warning("Failed to read local summary for video=%s", video.pk)

    if video.gcs_prefix and settings.GCS_BUCKET:
        gcs_path = f"{video.gcs_prefix}/summary/summary.md"
        try:
            from services.gcs_client import get_gcs_client
            gcs = get_gcs_client()
            text = gcs.download_as_text(gcs_path)
            if text:
                return text
        except Exception:
            logger.warning("Failed to read GCS summary for video=%s at %s", video.pk, gcs_path)

    return None
