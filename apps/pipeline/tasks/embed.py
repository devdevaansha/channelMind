import json
import logging
import pathlib

import django.utils.timezone as tz
from celery import shared_task
from django.conf import settings

from apps.channels.models import Video
from apps.jobs.models import Job
from apps.pipeline.progress import update_job_progress
from apps.pipeline.storage_policy import finalize_failed_job
from services.pinecone_client import PineconeClient

logger = logging.getLogger(__name__)

# Chunking parameters (in seconds)
_CHUNK_WINDOW_SEC = 30
_CHUNK_OVERLAP_SEC = 5


def _chunk_segments(segments: list[dict], window_sec: float, overlap_sec: float) -> list[dict]:
    """
    Group transcript segments into overlapping time windows.
    Returns list of {start, end, text} dicts.
    """
    if not segments:
        return []

    chunks = []
    i = 0
    while i < len(segments):
        chunk_start = segments[i]["start"]
        chunk_texts = []
        chunk_end = chunk_start

        j = i
        while j < len(segments) and segments[j]["start"] < chunk_start + window_sec:
            chunk_texts.append(segments[j]["text"])
            chunk_end = segments[j]["end"]
            j += 1

        chunks.append({
            "start": chunk_start,
            "end": chunk_end,
            "text": " ".join(chunk_texts).strip(),
        })

        # Advance, stepping back by overlap
        step_end = chunk_start + window_sec - overlap_sec
        while i < len(segments) and segments[i]["start"] < step_end:
            i += 1
        if i == j:  # safety: always advance at least one
            i += 1

    return [c for c in chunks if c["text"]]


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=1800,
    queue="pipeline",
    name="pipeline.embed_chunks",
)
def embed_chunks(self, job_id: str, video_id: str) -> None:
    """Stage G: Chunk transcript and embed via Vertex AI."""
    logger.info("embed_chunks start job=%s video=%s", job_id, video_id)

    try:
        video = Video.objects.select_related("channel").get(pk=video_id)
    except Video.DoesNotExist:
        return

    Job.objects.filter(pk=job_id).update(stage=Job.Stage.EMBED, updated_at=tz.now())
    update_job_progress(job_id, "embed", 0.0)

    if not video.transcript_local_path:
        logger.warning("No transcript for video=%s; skipping embed", video_id)
        update_job_progress(job_id, "embed", 1.0)
        return

    transcript_path = pathlib.Path(video.transcript_local_path)
    if not transcript_path.exists():
        update_job_progress(job_id, "embed", 1.0)
        return

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = transcript.get("segments", [])
    chunks = _chunk_segments(segments, _CHUNK_WINDOW_SEC, _CHUNK_OVERLAP_SEC)

    if not chunks:
        logger.warning("No chunks produced for video=%s", video_id)
        update_job_progress(job_id, "embed", 1.0)
        return

    channel_id = str(video.channel_id)
    chunk_dir = (
        pathlib.Path(settings.DATA_DIR)
        / "channels" / channel_id
        / "videos" / str(video_id)
        / "chunks"
    )
    chunk_dir.mkdir(parents=True, exist_ok=True)

    texts = [c["text"] for c in chunks]

    try:
        client = PineconeClient()
        embeddings = client.embed_texts(texts, input_type="passage")
    except Exception as exc:
        logger.exception("embed_chunks failed job=%s: %s", job_id, exc)
        if self.request.retries >= self.max_retries:
            finalize_failed_job(job_id, video_id, channel_id, exc)
            raise
        raise self.retry(exc=exc)

    # Write transcript chunks to disk (upsert task reads them)
    category_id = str(video.category_id) if video.category_id else ""
    source = f"https://www.youtube.com/watch?v={video.youtube_video_id}"
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        chunk_file = chunk_dir / f"chunk_{i:04d}.json"
        payload = {
            "chunk_index": i,
            "start": chunk["start"],
            "end": chunk["end"],
            "text": chunk["text"],
            "embedding": emb,
            "video_id": str(video_id),
            "youtube_video_id": video.youtube_video_id,
            "channel_id": channel_id,
            "title": video.title,
            "published_at": video.published_at.isoformat() if video.published_at else "",
            "category_id": category_id,
            "source": source,
        }
        chunk_file.write_text(json.dumps(payload), encoding="utf-8")

        if i % 10 == 0:
            update_job_progress(job_id, "embed", i / len(chunks))

    # Embed summary text if a summary exists
    summary_path = (
        pathlib.Path(video.summary_local_path) if video.summary_local_path else None
    )
    if summary_path and summary_path.exists():
        summary_text = summary_path.read_text(encoding="utf-8").strip()
        if summary_text:
            try:
                summary_embeddings = client.embed_texts([summary_text], input_type="passage")
                summary_file = chunk_dir / "summary_0000.json"
                summary_file.write_text(json.dumps({
                    "chunk_index": 0,
                    "text": summary_text,
                    "embedding": summary_embeddings[0],
                    "video_id": str(video_id),
                    "youtube_video_id": video.youtube_video_id,
                    "channel_id": channel_id,
                    "title": video.title,
                    "published_at": video.published_at.isoformat() if video.published_at else "",
                    "category_id": category_id,
                    "source": source,
                }), encoding="utf-8")
                logger.info("embed_chunks embedded summary for video=%s", video_id)
            except Exception as exc:
                logger.warning("Summary embedding failed (non-fatal): %s", exc)

    update_job_progress(job_id, "embed", 1.0)
    logger.info("embed_chunks done job=%s chunks=%d", job_id, len(chunks))
