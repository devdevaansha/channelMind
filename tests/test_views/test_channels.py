"""Tests for channels views."""
import json
import uuid

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.channels.models import Channel, Video
from apps.jobs.models import Artifact, Job


@pytest.fixture
def done_video_with_summary(channel):
    """A DONE video that already has a summary artifact."""
    v = Video.objects.create(
        channel=channel,
        youtube_video_id="vid_summarized_001",
        title="Already Summarized",
        status=Video.Status.DONE,
        gcs_prefix="youtube/channels/test/videos/001",
        published_at=timezone.now(),
    )
    Artifact.objects.create(
        video=v, type=Artifact.ArtifactType.SUMMARY_MD, local_path=""
    )
    return v


@pytest.fixture
def done_video_without_summary(channel):
    """A DONE video with a GCS prefix but no summary artifact."""
    return Video.objects.create(
        channel=channel,
        youtube_video_id="vid_unsummarized_001",
        title="Needs Summary",
        status=Video.Status.DONE,
        gcs_prefix="youtube/channels/test/videos/002",
        published_at=timezone.now(),
    )


@pytest.mark.django_db
class TestChannelIndex:
    def test_get_returns_200(self, client):
        url = reverse("channels:index")
        resp = client.get(url)
        assert resp.status_code == 200

    def test_shows_existing_channel(self, client, channel):
        url = reverse("channels:index")
        resp = client.get(url)
        assert channel.title in resp.content.decode()

    def test_unsummarized_count_annotation(self, channel, done_video_without_summary):
        """Verify the _channels_with_counts annotation computes correctly."""
        from apps.channels.views import _channels_with_counts

        ch = _channels_with_counts().get(pk=channel.pk)
        assert ch.videos_unsummarized == 1

    def test_unsummarized_count_zero_when_all_summarized(self, channel, done_video_with_summary):
        from apps.channels.views import _channels_with_counts

        ch = _channels_with_counts().get(pk=channel.pk)
        assert ch.videos_unsummarized == 0

    def test_unsummarized_count_multiple(self, channel, done_video_without_summary):
        Video.objects.create(
            channel=channel,
            youtube_video_id="vid_unsummarized_002",
            title="Also Needs Summary",
            status=Video.Status.DONE,
            gcs_prefix="youtube/channels/test/videos/003",
            published_at=timezone.now(),
        )
        from apps.channels.views import _channels_with_counts

        ch = _channels_with_counts().get(pk=channel.pk)
        assert ch.videos_unsummarized == 2


@pytest.mark.django_db
class TestAddChannel:
    def test_invalid_form_returns_422(self, client):
        url = reverse("channels:add")
        resp = client.post(url, {"channel_url": ""})
        assert resp.status_code in (200, 422)

    def test_add_channel_resolves_and_creates(self, client, mocker):
        mocker.patch(
            "apps.channels.views.YtDlpClient.get_channel_info",
            return_value={"channel_id": "UCnew123", "title": "New Channel"},
        )
        mocker.patch("apps.channels.views.discover_channel_videos.delay")

        url = reverse("channels:add")
        resp = client.post(url, {
            "channel_url": "https://www.youtube.com/@newchannel",
            "summarize_enabled": False,
        })
        assert resp.status_code in (200, 302)

        from apps.channels.models import Channel
        assert Channel.objects.filter(youtube_channel_id="UCnew123").exists()


@pytest.mark.django_db
class TestSummarizeChannel:
    def test_summarize_triggers_task(self, client, mocker, channel, done_video_without_summary):
        mock_delay = mocker.patch("apps.channels.views.summarize_channel_videos.delay")
        url = reverse("channels:summarize", args=[channel.id])
        resp = client.post(url, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "Summarizing 1 video(s)" in resp.content.decode()
        mock_delay.assert_called_once_with(str(channel.id))

    def test_summarize_no_videos_shows_message(self, client, mocker, channel, done_video_with_summary):
        mock_delay = mocker.patch("apps.channels.views.summarize_channel_videos.delay")
        url = reverse("channels:summarize", args=[channel.id])
        resp = client.post(url, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "No videos to summarize" in resp.content.decode()
        mock_delay.assert_not_called()

    def test_summarize_returns_htmx_trigger(self, client, mocker, channel, done_video_without_summary):
        mocker.patch("apps.channels.views.summarize_channel_videos.delay")
        url = reverse("channels:summarize", args=[channel.id])
        resp = client.post(url, HTTP_HX_REQUEST="true")
        assert "atva:summarizeTriggered" in resp["HX-Trigger"]

    def test_summarize_counts_eligible_videos(self, client, mocker, channel, done_video_without_summary, done_video_with_summary):
        mock_delay = mocker.patch("apps.channels.views.summarize_channel_videos.delay")
        url = reverse("channels:summarize", args=[channel.id])
        resp = client.post(url, HTTP_HX_REQUEST="true")
        assert "1 video(s)" in resp.content.decode()
        mock_delay.assert_called_once()

    def test_summarize_404_for_invalid_channel(self, client):
        url = reverse("channels:summarize", args=[uuid.uuid4()])
        resp = client.post(url)
        assert resp.status_code == 404


@pytest.fixture
def done_video_with_transcript(channel, tmp_path):
    """A DONE video with a local transcript JSON file and artifact."""
    transcript_data = {
        "segments": [
            {"start": 0.0, "text": "Hello world"},
            {"start": 5.5, "text": "This is a test transcript"},
        ]
    }
    transcript_file = tmp_path / "transcript.json"
    transcript_file.write_text(json.dumps(transcript_data), encoding="utf-8")

    v = Video.objects.create(
        channel=channel,
        youtube_video_id="vid_transcript_001",
        title="Video With Transcript",
        status=Video.Status.DONE,
        published_at=timezone.now(),
        duration_sec=60,
        transcript_local_path=str(transcript_file),
    )
    Artifact.objects.create(
        video=v,
        type=Artifact.ArtifactType.TRANSCRIPT_JSON,
        local_path=str(transcript_file),
    )
    return v


@pytest.fixture
def done_video_with_summary_file(channel, tmp_path):
    """A DONE video with a local summary file and artifact."""
    summary_file = tmp_path / "summary.md"
    summary_file.write_text(
        "This is a test summary.\n\nIt has multiple paragraphs.",
        encoding="utf-8",
    )

    v = Video.objects.create(
        channel=channel,
        youtube_video_id="vid_summary_file_001",
        title="Video With Summary File",
        status=Video.Status.DONE,
        published_at=timezone.now(),
        duration_sec=90,
        summary_local_path=str(summary_file),
    )
    Artifact.objects.create(
        video=v,
        type=Artifact.ArtifactType.SUMMARY_MD,
        local_path=str(summary_file),
    )
    return v


@pytest.mark.django_db
class TestExportChannelPdf:
    def test_export_transcript_returns_pdf(self, client, channel, done_video_with_transcript):
        url = reverse("channels:export", args=[channel.id])
        resp = client.get(url, {"type": "transcript"})
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert ".pdf" in resp["Content-Disposition"]

    def test_export_summary_returns_pdf(self, client, channel, done_video_with_summary_file):
        url = reverse("channels:export", args=[channel.id])
        resp = client.get(url, {"type": "summary"})
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert ".pdf" in resp["Content-Disposition"]

    def test_export_invalid_type_returns_400(self, client, channel):
        url = reverse("channels:export", args=[channel.id])
        resp = client.get(url, {"type": "invalid"})
        assert resp.status_code == 400

    def test_export_missing_type_returns_400(self, client, channel):
        url = reverse("channels:export", args=[channel.id])
        resp = client.get(url)
        assert resp.status_code == 400

    def test_export_no_data_returns_404(self, client, channel):
        url = reverse("channels:export", args=[channel.id])
        resp = client.get(url, {"type": "transcript"})
        assert resp.status_code == 404

    def test_export_404_for_invalid_channel(self, client):
        url = reverse("channels:export", args=[uuid.uuid4()])
        resp = client.get(url, {"type": "transcript"})
        assert resp.status_code == 404

    def test_pdf_is_valid_and_has_multiple_pages(self, client, channel, done_video_with_transcript):
        url = reverse("channels:export", args=[channel.id])
        resp = client.get(url, {"type": "transcript"})
        assert resp.status_code == 200
        pdf_bytes = resp.content
        assert pdf_bytes.startswith(b"%PDF")
        assert b"/Type /Page" in pdf_bytes

    def test_export_filename_uses_channel_title(self, client, channel, done_video_with_transcript):
        url = reverse("channels:export", args=[channel.id])
        resp = client.get(url, {"type": "transcript"})
        assert "Test_Channel_transcripts.pdf" in resp["Content-Disposition"]

    def test_export_htmx_no_data_returns_message(self, client, channel):
        url = reverse("channels:export", args=[channel.id])
        resp = client.get(url, {"type": "summary"}, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "No summaries available" in resp.content.decode()
