"""
Pytest configuration and shared fixtures.
"""
import uuid
import pytest
from django.utils import timezone


@pytest.fixture
def channel(db):
    from apps.channels.models import Channel
    return Channel.objects.create(
        youtube_channel_id="UCtest123",
        title="Test Channel",
        summarize_enabled=False,
    )


@pytest.fixture
def category(db):
    from apps.channels.models import Category
    return Category.objects.create(name="Technology", created_by="test")


@pytest.fixture
def video(db, channel):
    from apps.channels.models import Video
    return Video.objects.create(
        channel=channel,
        youtube_video_id="dQw4w9WgXcQ",
        title="Test Video",
        duration_sec=120,
        published_at=timezone.now(),
        status=Video.Status.QUEUED,
    )


@pytest.fixture
def job(db, video):
    from apps.jobs.models import Job
    return Job.objects.create(video=video)


@pytest.fixture(autouse=True)
def use_eager_celery(settings):
    """Run Celery tasks synchronously in tests (no worker needed)."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


@pytest.fixture
def mock_redis(mocker):
    """Prevent real Redis connections in tests."""
    mock = mocker.patch("redis.from_url")
    mock.return_value.publish = mocker.MagicMock(return_value=1)
    pubsub = mocker.MagicMock()
    pubsub.listen.return_value = iter([])
    mock.return_value.pubsub.return_value = pubsub
    return mock
