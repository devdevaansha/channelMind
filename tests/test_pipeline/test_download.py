"""Tests for download pipeline task."""
import pathlib
import pytest


@pytest.mark.django_db
class TestDownloadAudio:
    def test_download_succeeds(self, job, video, mocker, tmp_path):
        from apps.pipeline.tasks.download import download_audio
        from apps.channels.models import Video
        from apps.jobs.models import Job

        # Mock YtDlpClient.download to create a fake audio file
        audio_path = tmp_path / "audio.m4a"
        audio_path.write_bytes(b"fake audio")
        mocker.patch("apps.pipeline.tasks.download.YtDlpClient.download", return_value=audio_path)
        mocker.patch("apps.pipeline.tasks.download.update_job_progress")
        mocker.patch("django.conf.settings.DATA_DIR", str(tmp_path))

        download_audio(str(job.id), str(video.id))

        video.refresh_from_db()
        assert video.status == Video.Status.PROCESSING

    def test_download_retries_on_failure(self, job, video, mocker, tmp_path):
        from apps.pipeline.tasks.download import download_audio
        from apps.jobs.models import Job

        mocker.patch(
            "apps.pipeline.tasks.download.YtDlpClient.download",
            side_effect=Exception("yt-dlp error"),
        )
        mocker.patch("apps.pipeline.tasks.download.update_job_progress")
        mocker.patch("django.conf.settings.DATA_DIR", str(tmp_path))

        with pytest.raises(Exception):
            download_audio(str(job.id), str(video.id))

        job.refresh_from_db()
        assert job.status == Job.Status.FAILED
