from django.urls import path
from . import views

app_name = "library"

urlpatterns = [
    path("", views.index, name="index"),
    path("<uuid:video_id>/", views.video_detail, name="detail"),
    path("<uuid:video_id>/category/", views.assign_category, name="assign_category"),
]
