from django.urls import path
from . import views

app_name = "channels"

urlpatterns = [
    path("", views.index, name="index"),
    path("add/", views.add_channel, name="add"),
    path("<uuid:channel_id>/sync/", views.sync_channel, name="sync"),
    path("<uuid:channel_id>/summarize/", views.summarize_channel, name="summarize"),
    path("<uuid:channel_id>/export/", views.export_channel_pdf, name="export"),
]
