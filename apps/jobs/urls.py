from django.urls import path
from . import views

app_name = "jobs"

urlpatterns = [
    path("", views.index, name="index"),
    path("<uuid:job_id>/stream/", views.job_progress_stream, name="stream"),
    path("<uuid:job_id>/detail/", views.job_detail, name="detail"),
    path("<uuid:job_id>/retry/", views.retry_job, name="retry"),
]
