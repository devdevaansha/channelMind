"""Tests for library views — transcript/summary loading with GCS fallback."""
import json
import pytest
from django.urls import reverse
from apps.channels.models import Video


SAMPLE_TRANSCRIPT = {
    "segments": [
        {"start": 0.0, "end": 5.0, "text": "Hello world"},
        {"start": 5.0, "end": 10.0, "text": "This is a test"},
    ]
}

SAMPLE_SUMMARY = "## Summary\n\nGreat video about testing."


@pytest.mark.django_db
class TestLibraryIndex:
    def test_get_returns_200(self, client):
        resp = client.get(reverse("library:index"))
        assert resp.status_code == 200

    def test_shows_video_in_list(self, client, video):
        resp = client.get(reverse("library:index"))
        assert video.title in resp.content.decode()

    def test_filter_by_channel(self, client, video):
        resp = client.get(reverse("library:index"), {"channel": str(video.channel_id)})
        assert video.title in resp.content.decode()


@pytest.mark.django_db
class TestVideoDetailLocal:
    """Transcript/summary loaded from local files."""

    def test_transcript_from_local_file(self, client, video, tmp_path):
        tp = tmp_path / "transcript.json"
        tp.write_text(json.dumps(SAMPLE_TRANSCRIPT), encoding="utf-8")
        Video.objects.filter(pk=video.pk).update(transcript_local_path=str(tp))

        resp = client.get(reverse("library:detail", args=[video.pk]))
        body = resp.content.decode()
        assert resp.status_code == 200
        assert "Hello world" in body

    def test_summary_from_local_file(self, client, video, tmp_path):
        sp = tmp_path / "summary.md"
        sp.write_text(SAMPLE_SUMMARY, encoding="utf-8")
        Video.objects.filter(pk=video.pk).update(summary_local_path=str(sp))

        resp = client.get(reverse("library:detail", args=[video.pk]))
        body = resp.content.decode()
        assert resp.status_code == 200
        assert "Great video about testing" in body

    def test_no_transcript_shows_empty_state(self, client, video):
        resp = client.get(reverse("library:detail", args=[video.pk]))
        body = resp.content.decode()
        assert "No transcript available" in body


@pytest.mark.django_db
class TestVideoDetailGCSFallback:
    """Transcript/summary loaded from GCS when local files are missing."""

    def test_transcript_falls_back_to_gcs(self, client, video, mocker, settings):
        settings.GCS_BUCKET = "test-bucket"
        Video.objects.filter(pk=video.pk).update(
            transcript_local_path="",
            gcs_prefix=f"youtube/channels/{video.channel_id}/videos/{video.pk}",
        )

        mock_gcs = mocker.MagicMock()
        mock_gcs.download_as_text.return_value = json.dumps(SAMPLE_TRANSCRIPT)
        mocker.patch(
            "apps.library.loaders.get_gcs_client",
            return_value=mock_gcs,
        )

        resp = client.get(reverse("library:detail", args=[video.pk]))
        body = resp.content.decode()
        assert resp.status_code == 200
        assert "Hello world" in body

        expected_path = f"youtube/channels/{video.channel_id}/videos/{video.pk}/transcript/transcript.json"
        mock_gcs.download_as_text.assert_any_call(expected_path)

    def test_summary_falls_back_to_gcs(self, client, video, mocker, settings):
        settings.GCS_BUCKET = "test-bucket"
        Video.objects.filter(pk=video.pk).update(
            summary_local_path="",
            gcs_prefix=f"youtube/channels/{video.channel_id}/videos/{video.pk}",
        )

        mock_gcs = mocker.MagicMock()
        mock_gcs.download_as_text.side_effect = lambda path: {
            f"youtube/channels/{video.channel_id}/videos/{video.pk}/transcript/transcript.json": json.dumps(SAMPLE_TRANSCRIPT),
            f"youtube/channels/{video.channel_id}/videos/{video.pk}/summary/summary.md": SAMPLE_SUMMARY,
        }.get(path)
        mocker.patch(
            "apps.library.loaders.get_gcs_client",
            return_value=mock_gcs,
        )

        resp = client.get(reverse("library:detail", args=[video.pk]))
        body = resp.content.decode()
        assert resp.status_code == 200
        assert "Great video about testing" in body

    def test_no_gcs_prefix_shows_empty_state(self, client, video, settings):
        settings.GCS_BUCKET = "test-bucket"
        Video.objects.filter(pk=video.pk).update(
            transcript_local_path="",
            summary_local_path="",
            gcs_prefix="",
        )

        resp = client.get(reverse("library:detail", args=[video.pk]))
        body = resp.content.decode()
        assert resp.status_code == 200
        assert "No transcript available" in body

    def test_gcs_error_shows_empty_state(self, client, video, mocker, settings):
        settings.GCS_BUCKET = "test-bucket"
        Video.objects.filter(pk=video.pk).update(
            transcript_local_path="",
            gcs_prefix=f"youtube/channels/{video.channel_id}/videos/{video.pk}",
        )

        mock_gcs = mocker.MagicMock()
        mock_gcs.download_as_text.side_effect = Exception("Connection error")
        mocker.patch(
            "apps.library.loaders.get_gcs_client",
            return_value=mock_gcs,
        )

        resp = client.get(reverse("library:detail", args=[video.pk]))
        body = resp.content.decode()
        assert resp.status_code == 200
        assert "No transcript available" in body
