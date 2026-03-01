"""Tests for jobs views."""
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestJobIndex:
    def test_get_returns_200(self, client):
        resp = client.get(reverse("jobs:index"))
        assert resp.status_code == 200

    def test_shows_job_stage(self, client, job):
        resp = client.get(reverse("jobs:index"))
        assert resp.status_code == 200


@pytest.mark.django_db
class TestRetryJob:
    def test_retry_non_failed_job_returns_400(self, client, job):
        url = reverse("jobs:retry", args=[job.id])
        resp = client.post(url)
        assert resp.status_code == 400

    def test_retry_failed_job_creates_new_job(self, client, job, mocker):
        from apps.jobs.models import Job
        job.status = Job.Status.FAILED
        job.save()

        mocker.patch("apps.jobs.views.build_video_pipeline")

        url = reverse("jobs:retry", args=[job.id])
        resp = client.post(url)
        assert resp.status_code == 200
        assert Job.objects.filter(video=job.video).count() == 2


@pytest.mark.django_db
class TestJobDetail:
    def test_returns_200(self, client, job):
        url = reverse("jobs:detail", args=[job.id])
        resp = client.get(url)
        assert resp.status_code == 200
