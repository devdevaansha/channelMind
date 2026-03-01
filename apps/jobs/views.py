import json
import logging

from django.http import HttpResponse, HttpResponseBadRequest, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from apps.channels.models import Video
from apps.pipeline.chains import build_video_pipeline

from .models import Job

logger = logging.getLogger(__name__)


def index(request):
    """Tab 2: Job monitor table."""
    jobs = Job.objects.select_related("video__channel").order_by("-created_at")[:200]
    live_job_ids = list(
        Job.objects.filter(status=Job.Status.RUNNING)
        .order_by("-created_at")
        .values_list("id", flat=True)[:20]
    )
    return render(request, "jobs/index.html", {"jobs": jobs, "live_job_ids": live_job_ids})


@require_GET
def job_progress_stream(request, job_id):
    """
    SSE endpoint: streams job progress events from Redis pub/sub.

    IMPORTANT: Requires gunicorn with gevent workers. Sync workers will block
    on this generator and exhaust the worker pool.

    Client subscribes via HTMX SSE extension:
        hx-ext="sse" sse-connect="/jobs/<id>/stream/"
    """
    import redis
    from django.conf import settings

    # If Redis is unavailable, don't crash a gunicorn worker in the generator.
    try:
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        r.ping()
    except Exception as exc:
        logger.warning("SSE unavailable for job=%s: %s", job_id, exc)
        return HttpResponse("SSE temporarily unavailable", status=503)

    def event_stream():
        pubsub = r.pubsub()
        pubsub.subscribe(f"job_progress:{job_id}")

        try:
            for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                yield f"data: {data}\n\n"
                try:
                    parsed = json.loads(data)
                    if parsed.get("progress", 0) >= 100:
                        break
                except json.JSONDecodeError:
                    pass
        finally:
            pubsub.unsubscribe()
            pubsub.close()

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # prevent nginx from buffering SSE
    return response


def job_detail(request, job_id):
    """Job detail view (loaded as HTMX modal)."""
    job = get_object_or_404(Job.objects.select_related("video__channel"), pk=job_id)
    artifacts = job.video.artifacts.all()
    return render(request, "jobs/_job_detail_modal.html", {"job": job, "artifacts": artifacts})


@require_POST
def retry_job(request, job_id):
    """Re-enqueue a failed job."""
    job = get_object_or_404(Job, pk=job_id)
    if job.status != Job.Status.FAILED:
        return HttpResponseBadRequest("Job is not in failed state")

    new_job = Job.objects.create(video=job.video)
    pipeline = build_video_pipeline(
        str(new_job.id),
        str(job.video_id),
        summarize=job.video.channel.summarize_enabled,
    )
    pipeline.delay()

    if request.headers.get("HX-Request"):
        return render(request, "jobs/_job_row.html", {"job": new_job})

    return render(request, "jobs/index.html", {"jobs": Job.objects.select_related("video__channel").order_by("-created_at")[:200]})
