"""
Progress tracking for the video pipeline.

Each stage has a weight (percentage of total progress it contributes).
Weights must sum to 100.

update_job_progress() updates the Job row in DB and publishes an SSE event
to the Redis pub/sub channel `job_progress:<job_id>`.
The SSE view in apps/jobs/views.py subscribes and streams to the browser.
"""
import json
import logging

logger = logging.getLogger(__name__)

# Stage weights (must sum to 100)
STAGE_WEIGHTS: dict[str, int] = {
    "fetch":      5,
    "download":  20,
    "transcribe": 35,
    "upload":    10,
    "categorize":  5,
    "summarize": 10,
    "embed":     10,
    "upsert":     5,
}

# Pre-compute the cumulative start progress for each stage
STAGE_START: dict[str, int] = {}
_cumulative = 0
for _stage, _weight in STAGE_WEIGHTS.items():
    STAGE_START[_stage] = _cumulative
    _cumulative += _weight


def compute_overall(stage: str, pct_within_stage: float) -> int:
    """
    Compute overall progress (0-100) given a stage and within-stage completion.
    pct_within_stage: 0.0 to 1.0
    """
    weight = STAGE_WEIGHTS.get(stage, 0)
    base = STAGE_START.get(stage, 0)
    return min(int(base + weight * pct_within_stage), 100)


def update_job_progress(job_id: str, stage: str, pct_within_stage: float) -> None:
    """
    Update the Job row in the database and publish an SSE progress event.

    IMPORTANT: Uses QuerySet.update() which bypasses auto_now.
    updated_at is set explicitly.
    """
    import django.utils.timezone as tz
    from apps.jobs.models import Job

    overall = compute_overall(stage, pct_within_stage)

    Job.objects.filter(pk=job_id).update(
        stage=stage,
        progress=overall,
        status=Job.Status.RUNNING,
        updated_at=tz.now(),
    )

    _publish_sse(job_id, stage, overall)


def _publish_sse(job_id: str, stage: str, progress: int) -> None:
    """Publish a progress event to Redis pub/sub for SSE streaming."""
    try:
        import redis
        from django.conf import settings

        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        payload = json.dumps({
            "job_id": str(job_id),
            "stage": stage,
            "progress": progress,
        })
        r.publish(f"job_progress:{job_id}", payload)
    except Exception as e:
        # Never let SSE publishing crash a pipeline task
        logger.warning("Failed to publish SSE for job=%s: %s", job_id, e)
