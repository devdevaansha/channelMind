import json
import logging
import pathlib

from celery import shared_task
from django.conf import settings
import django.utils.timezone as tz

from apps.channels.models import Video
from apps.jobs.models import Job, VectorIndexItem
from apps.pipeline.progress import update_job_progress
from apps.pipeline.storage_policy import finalize_failed_job, finalize_succeeded_job
from services.pinecone_client import PineconeClient

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "llama-text-embed-v2"
_CHUNKING_VERSION = "v1"


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="pipeline",
    name="pipeline.upsert_to_pinecone",
)
def upsert_to_pinecone(self, job_id: str, video_id: str) -> None:
    """Stage H: Upsert chunk embeddings into Pinecone."""
    logger.info("upsert_to_pinecone start job=%s video=%s", job_id, video_id)

    try:
        video = Video.objects.select_related("channel").get(pk=video_id)
    except Video.DoesNotExist:
        return

    Job.objects.filter(pk=job_id).update(stage=Job.Stage.UPSERT, updated_at=tz.now())
    update_job_progress(job_id, "upsert", 0.0)

    channel_id = str(video.channel_id)
    chunk_dir = (
        pathlib.Path(settings.DATA_DIR)
        / "channels" / channel_id
        / "videos" / str(video_id)
        / "chunks"
    )

    chunk_files = sorted(chunk_dir.glob("chunk_*.json")) if chunk_dir.exists() else []
    summary_files = sorted(chunk_dir.glob("summary_*.json")) if chunk_dir.exists() else []

    if not chunk_files and not summary_files:
        logger.warning("No chunk files for video=%s; skipping upsert", video_id)
        _finish_job(job_id, video_id)
        return

    vectors = []

    for cf in chunk_files:
        payload = json.loads(cf.read_text(encoding="utf-8"))
        vector_id = f"{video_id}:t:{payload['chunk_index']:04d}"
        vectors.append({
            "id": vector_id,
            "values": payload["embedding"],
            "metadata": {
                "video_id": str(video_id),
                "youtube_video_id": payload.get("youtube_video_id", ""),
                "channel_id": payload.get("channel_id", ""),
                "title": payload.get("title", ""),
                "published_at": payload.get("published_at", ""),
                "category_id": payload.get("category_id", ""),
                "chunk_index": payload.get("chunk_index", 0),
                "start": payload.get("start", 0),
                "end": payload.get("end", 0),
                "text": payload.get("text", "")[:4000],  # Pinecone 40KB metadata limit guard
                "source": payload.get("source", ""),
                "type": "transcript",
            },
        })

    for sf in summary_files:
        payload = json.loads(sf.read_text(encoding="utf-8"))
        vector_id = f"{video_id}:s:{payload['chunk_index']:04d}"
        vectors.append({
            "id": vector_id,
            "values": payload["embedding"],
            "metadata": {
                "video_id": str(video_id),
                "youtube_video_id": payload.get("youtube_video_id", ""),
                "channel_id": payload.get("channel_id", ""),
                "title": payload.get("title", ""),
                "published_at": payload.get("published_at", ""),
                "category_id": payload.get("category_id", ""),
                "chunk_index": payload.get("chunk_index", 0),
                "text": payload.get("text", "")[:4000],
                "source": payload.get("source", ""),
                "type": "summary",
            },
        })

    try:
        pc = PineconeClient()
        namespace = channel_id  # one namespace per channel
        pc.upsert_vectors(vectors, namespace=namespace)
    except Exception as exc:
        logger.exception("upsert_to_pinecone failed job=%s: %s", job_id, exc)
        if self.request.retries >= self.max_retries:
            finalize_failed_job(job_id, video_id, channel_id, exc)
            raise
        raise self.retry(exc=exc)

    # Record which vectors we stored
    for v in vectors:
        VectorIndexItem.objects.get_or_create(
            pinecone_vector_id=v["id"],
            defaults={
                "video_id": video_id,
                "pinecone_namespace": namespace,
                "embedding_model": _EMBEDDING_MODEL,
                "chunking_version": _CHUNKING_VERSION,
            },
        )

    update_job_progress(job_id, "upsert", 1.0)
    _finish_job(job_id, video_id)
    logger.info("upsert_to_pinecone done job=%s vectors=%d", job_id, len(vectors))


def _finish_job(job_id: str, video_id: str) -> None:
    channel_id = Video.objects.values_list("channel_id", flat=True).get(pk=video_id)
    finalize_succeeded_job(job_id, video_id, str(channel_id))
