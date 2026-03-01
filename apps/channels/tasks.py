import logging

import django.utils.timezone as tz
from celery import shared_task
from django.db.models import Count

from apps.channels.models import Channel, Video
from apps.jobs.models import Artifact, Job
from apps.pipeline.progress import update_job_progress

logger = logging.getLogger(__name__)


@shared_task(name="channels.sync_all_channels")
def sync_all_channels() -> None:
    """Beat task: trigger discovery for all channels."""
    channel_ids = list(Channel.objects.values_list("id", flat=True))
    logger.info("sync_all_channels: syncing %d channels", len(channel_ids))
    for channel_id in channel_ids:
        discover_channel_videos.delay(str(channel_id))


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    name="channels.discover_channel_videos",
)
def discover_channel_videos(self, channel_id: str) -> None:
    """
    Stage A: Discover new videos for a channel and enqueue the pipeline for each.
    """
    logger.info("discover_channel_videos start channel=%s", channel_id)

    try:
        channel = Channel.objects.get(pk=channel_id)
    except Channel.DoesNotExist:
        logger.error("Channel not found: %s", channel_id)
        return

    from services.ytdlp_client import YtDlpClient

    try:
        client = YtDlpClient()
        video_metas = client.list_channel_videos(
            channel.youtube_channel_id,
            after=channel.sync_cursor,
        )
    except Exception as exc:
        logger.exception("discover_channel_videos failed channel=%s: %s", channel_id, exc)
        raise self.retry(exc=exc)

    # Mark sync as "happened" immediately after successful listing.
    now = tz.now()
    update_kwargs: dict = {"last_synced_at": now}
    if video_metas:
        update_kwargs["sync_cursor"] = video_metas[0]["id"]
    Channel.objects.filter(pk=channel_id).update(**update_kwargs)

    new_count = 0
    for meta in video_metas:
        video, created = Video.objects.get_or_create(
            youtube_video_id=meta["id"],
            defaults={
                "channel": channel,
                "title": meta["title"],
                "published_at": meta["published_at"],
                "duration_sec": meta["duration"],
                "status": Video.Status.QUEUED,
            },
        )
        if created:
            new_count += 1
            logger.info("Discovered new video: %s (%s)", meta["title"], meta["id"])

            from apps.pipeline.chains import build_video_pipeline

            job = Job.objects.create(video=video)
            pipeline = build_video_pipeline(
                str(job.id),
                str(video.id),
                summarize=channel.summarize_enabled,
            )
            pipeline.delay()
            logger.info("Enqueued pipeline for video=%s job=%s", video.id, job.id)

    # If a previous discovery run was interrupted after creating Video rows but before
    # creating Job rows, backfill jobs for queued videos without any jobs.
    backlog_video_ids = list(
        Video.objects.filter(
            channel=channel,
            status__in=[Video.Status.QUEUED, Video.Status.DISCOVERED],
        )
        .annotate(job_count=Count("jobs"))
        .filter(job_count=0)
        .values_list("id", flat=True)[:500]
    )
    if backlog_video_ids:
        from apps.pipeline.chains import build_video_pipeline

        logger.warning(
            "Backfilling %d jobs for channel=%s (previous run likely interrupted)",
            len(backlog_video_ids),
            channel_id,
        )
        for vid in backlog_video_ids:
            job = Job.objects.create(video_id=vid)
            pipeline = build_video_pipeline(
                str(job.id),
                str(vid),
                summarize=channel.summarize_enabled,
            )
            pipeline.delay()

    logger.info(
        "discover_channel_videos done channel=%s new=%d",
        channel_id, new_count,
    )


@shared_task(
    bind=True,
    max_retries=1,
    default_retry_delay=30,
    name="channels.summarize_channel_videos",
)
def summarize_channel_videos(self, channel_id: str) -> None:
    """
    Find all DONE videos for a channel that have not been summarized
    and kick off the summarize-only pipeline (restore → summarize → embed → upsert)
    for each one.
    """
    logger.info("summarize_channel_videos start channel=%s", channel_id)

    try:
        channel = Channel.objects.get(pk=channel_id)
    except Channel.DoesNotExist:
        logger.error("Channel not found: %s", channel_id)
        return

    eligible_videos = list(
        Video.objects.filter(
            channel=channel,
            status=Video.Status.DONE,
            gcs_prefix__gt="",
        )
        .exclude(artifacts__type=Artifact.ArtifactType.SUMMARY_MD)
        .values_list("id", flat=True)
    )

    if not eligible_videos:
        logger.info("No unsummarized videos for channel=%s", channel_id)
        return

    from apps.pipeline.chains import build_summarize_only_pipeline

    for vid in eligible_videos:
        job = Job.objects.create(video_id=vid)
        pipeline = build_summarize_only_pipeline(str(job.id), str(vid))
        pipeline.delay()
        logger.info("Enqueued summarize pipeline for video=%s job=%s", vid, job.id)

    logger.info(
        "summarize_channel_videos done channel=%s enqueued=%d",
        channel_id, len(eligible_videos),
    )
