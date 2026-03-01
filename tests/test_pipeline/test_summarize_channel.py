"""Tests for the summarize_channel_videos task and build_summarize_only_pipeline chain."""
import pytest
from django.utils import timezone

from apps.channels.models import Channel, Video
from apps.jobs.models import Artifact, Job


@pytest.fixture
def summarize_channel(db):
    return Channel.objects.create(
        youtube_channel_id="UCsummarize_test",
        title="Summarize Test Channel",
        summarize_enabled=False,
    )


@pytest.fixture
def done_video_no_summary(summarize_channel):
    return Video.objects.create(
        channel=summarize_channel,
        youtube_video_id="vid_needs_summary",
        title="Needs Summary",
        status=Video.Status.DONE,
        gcs_prefix="youtube/channels/test/videos/needs_summary",
        published_at=timezone.now(),
    )


@pytest.fixture
def done_video_has_summary(summarize_channel):
    v = Video.objects.create(
        channel=summarize_channel,
        youtube_video_id="vid_has_summary",
        title="Has Summary",
        status=Video.Status.DONE,
        gcs_prefix="youtube/channels/test/videos/has_summary",
        published_at=timezone.now(),
    )
    Artifact.objects.create(
        video=v, type=Artifact.ArtifactType.SUMMARY_MD, local_path=""
    )
    return v


@pytest.fixture
def queued_video(summarize_channel):
    return Video.objects.create(
        channel=summarize_channel,
        youtube_video_id="vid_queued",
        title="Still Queued",
        status=Video.Status.QUEUED,
        published_at=timezone.now(),
    )


@pytest.mark.django_db
class TestSummarizeChannelVideosTask:
    def test_enqueues_pipeline_for_unsummarized_videos(
        self, mocker, summarize_channel, done_video_no_summary
    ):
        mock_pipeline = mocker.MagicMock()
        mock_build = mocker.patch(
            "apps.pipeline.chains.build_summarize_only_pipeline",
            return_value=mock_pipeline,
        )

        from apps.channels.tasks import summarize_channel_videos

        summarize_channel_videos(str(summarize_channel.id))

        mock_build.assert_called_once()
        mock_pipeline.delay.assert_called_once()

        job = Job.objects.filter(video=done_video_no_summary).first()
        assert job is not None

    def test_skips_videos_that_already_have_summaries(
        self, mocker, summarize_channel, done_video_has_summary
    ):
        mock_build = mocker.patch(
            "apps.pipeline.chains.build_summarize_only_pipeline",
        )

        from apps.channels.tasks import summarize_channel_videos

        summarize_channel_videos(str(summarize_channel.id))

        mock_build.assert_not_called()

    def test_skips_non_done_videos(
        self, mocker, summarize_channel, queued_video
    ):
        mock_build = mocker.patch(
            "apps.pipeline.chains.build_summarize_only_pipeline",
        )

        from apps.channels.tasks import summarize_channel_videos

        summarize_channel_videos(str(summarize_channel.id))

        mock_build.assert_not_called()

    def test_skips_videos_without_gcs_prefix(self, mocker, summarize_channel):
        Video.objects.create(
            channel=summarize_channel,
            youtube_video_id="vid_no_gcs",
            title="No GCS",
            status=Video.Status.DONE,
            gcs_prefix="",
            published_at=timezone.now(),
        )
        mock_build = mocker.patch(
            "apps.pipeline.chains.build_summarize_only_pipeline",
        )

        from apps.channels.tasks import summarize_channel_videos

        summarize_channel_videos(str(summarize_channel.id))

        mock_build.assert_not_called()

    def test_handles_missing_channel_gracefully(self, mocker):
        import uuid
        mock_build = mocker.patch(
            "apps.pipeline.chains.build_summarize_only_pipeline",
        )

        from apps.channels.tasks import summarize_channel_videos

        summarize_channel_videos(str(uuid.uuid4()))

        mock_build.assert_not_called()

    def test_enqueues_multiple_videos(self, mocker, summarize_channel, done_video_no_summary):
        Video.objects.create(
            channel=summarize_channel,
            youtube_video_id="vid_needs_summary_2",
            title="Also Needs Summary",
            status=Video.Status.DONE,
            gcs_prefix="youtube/channels/test/videos/needs_summary_2",
            published_at=timezone.now(),
        )
        mock_pipeline = mocker.MagicMock()
        mocker.patch(
            "apps.pipeline.chains.build_summarize_only_pipeline",
            return_value=mock_pipeline,
        )

        from apps.channels.tasks import summarize_channel_videos

        summarize_channel_videos(str(summarize_channel.id))

        assert mock_pipeline.delay.call_count == 2
        assert Job.objects.filter(
            video__channel=summarize_channel
        ).count() == 2


@pytest.mark.django_db
class TestBuildSummarizeOnlyPipeline:
    def test_chain_has_four_tasks(self):
        from apps.pipeline.chains import build_summarize_only_pipeline

        c = build_summarize_only_pipeline("fake-job-id", "fake-video-id")

        task_names = []
        current = c
        while current:
            if hasattr(current, "task"):
                task_names.append(current.task)
            if hasattr(current, "tasks") and current.tasks:
                for t in current.tasks:
                    task_names.append(t.task)
                break
            current = getattr(current, "parent", None) or getattr(current, "body", None)

        assert "pipeline.restore_transcript" in task_names
        assert "pipeline.summarize_video" in task_names
        assert "pipeline.embed_chunks" in task_names
        assert "pipeline.upsert_to_pinecone" in task_names
