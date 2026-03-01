"""Unit tests for Django models."""
import pytest
from django.utils import timezone


@pytest.mark.django_db
class TestCategory:
    def test_str(self, category):
        assert str(category) == "Technology"

    def test_unique_name(self, category):
        from apps.channels.models import Category
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            Category.objects.create(name="Technology")


@pytest.mark.django_db
class TestChannel:
    def test_str_uses_title(self, channel):
        assert str(channel) == "Test Channel"

    def test_str_falls_back_to_channel_id(self, db):
        from apps.channels.models import Channel
        ch = Channel.objects.create(youtube_channel_id="UCno_title", title="")
        assert str(ch) == "UCno_title"

    def test_summarize_disabled_by_default(self, channel):
        assert channel.summarize_enabled is False


@pytest.mark.django_db
class TestVideo:
    def test_youtube_url(self, video):
        assert video.youtube_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_default_status_queued(self, video):
        from apps.channels.models import Video
        assert video.status == Video.Status.QUEUED

    def test_unique_youtube_video_id(self, video, channel):
        from apps.channels.models import Video
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            Video.objects.create(
                channel=channel,
                youtube_video_id="dQw4w9WgXcQ",
                title="Duplicate",
            )


@pytest.mark.django_db
class TestJob:
    def test_default_status_queued(self, job):
        from apps.jobs.models import Job
        assert job.status == Job.Status.QUEUED

    def test_duration_sec_none_when_not_finished(self, job):
        assert job.duration_sec is None

    def test_duration_sec_calculated(self, job):
        from datetime import timedelta
        now = timezone.now()
        job.started_at = now - timedelta(seconds=30)
        job.finished_at = now
        job.save()
        assert abs(job.duration_sec - 30) < 1


@pytest.mark.django_db
class TestProgressWeights:
    def test_weights_sum_to_100(self):
        from apps.pipeline.progress import STAGE_WEIGHTS
        assert sum(STAGE_WEIGHTS.values()) == 100

    def test_compute_overall_start(self):
        from apps.pipeline.progress import compute_overall
        assert compute_overall("fetch", 0.0) == 0

    def test_compute_overall_end(self):
        from apps.pipeline.progress import compute_overall
        assert compute_overall("upsert", 1.0) == 100

    def test_compute_overall_mid_download(self):
        from apps.pipeline.progress import compute_overall, STAGE_START, STAGE_WEIGHTS
        # Download starts at 5 (after fetch=5%) and has weight 20
        expected = STAGE_START["download"] + int(STAGE_WEIGHTS["download"] * 0.5)
        assert compute_overall("download", 0.5) == expected
