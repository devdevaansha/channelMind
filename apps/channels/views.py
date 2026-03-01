import logging
import json
import re

from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from apps.channels.pdf import build_channel_pdf
from apps.channels.tasks import discover_channel_videos, summarize_channel_videos
from apps.jobs.models import Artifact
from apps.library.loaders import load_transcript, load_summary
from services.ytdlp_client import YtDlpClient

from .forms import AddChannelForm
from .models import Category, Channel, Video

logger = logging.getLogger(__name__)


def _channels_with_counts():
    """Return Channel queryset annotated with video totals and unsummarized count."""
    unsummarized_sq = (
        Video.objects.filter(
            channel_id=OuterRef("pk"),
            status=Video.Status.DONE,
        )
        .exclude(artifacts__type=Artifact.ArtifactType.SUMMARY_MD)
        .order_by()
        .values("channel_id")
        .annotate(cnt=Count("id"))
        .values("cnt")
    )
    return Channel.objects.annotate(
        videos_total=Count("videos", distinct=True),
        videos_done=Count(
            "videos", filter=Q(videos__status=Video.Status.DONE), distinct=True,
        ),
        videos_unsummarized=Coalesce(
            Subquery(unsummarized_sq, output_field=IntegerField()),
            Value(0),
        ),
    )


def index(request):
    """Tab 1: Channel list + add form."""
    channels = _channels_with_counts().order_by("-created_at")
    form = AddChannelForm()
    return render(request, "channels/index.html", {
        "channels": channels,
        "form": form,
        "categories": Category.objects.all(),
    })


@require_POST
def add_channel(request):
    """Handle add-channel form. Returns HTMX partial of new channel row."""
    is_ajax = (
        request.headers.get("X-Atva-Ajax") == "1"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )
    form = AddChannelForm(request.POST)
    if not form.is_valid():
        if is_ajax:
            return JsonResponse(
                {"form_html": render_to_string("channels/_add_form.html", {"form": form}, request=request)},
                status=422,
            )
        return render(request, "channels/_add_form.html", {"form": form}, status=422)

    channel_url = form.cleaned_data["channel_url"].strip()
    summarize = form.cleaned_data["summarize_enabled"]
    default_category = form.cleaned_data.get("default_category")

    # Resolve channel ID and title via yt-dlp
    try:
        client = YtDlpClient()
        info = client.get_channel_info(channel_url)
        channel_id = info["channel_id"]
        title = info["title"]
    except Exception as e:
        logger.warning("Could not resolve channel URL '%s': %s", channel_url, e)
        form.add_error("channel_url", f"Could not resolve channel: {e}")
        if is_ajax:
            return JsonResponse(
                {"form_html": render_to_string("channels/_add_form.html", {"form": form}, request=request)},
                status=422,
            )
        return render(request, "channels/_add_form.html", {"form": form}, status=422)

    channel, created = Channel.objects.get_or_create(
        youtube_channel_id=channel_id,
        defaults={
            "title": title,
            "summarize_enabled": summarize,
            "default_category": default_category,
        },
    )
    if not created:
        # Update settings even if channel already exists
        channel.summarize_enabled = summarize
        channel.default_category = default_category
        channel.save(update_fields=["summarize_enabled", "default_category"])

    # Trigger discovery
    discover_channel_videos.delay(str(channel.id))

    # Ensure counts exist when rendering the row partial.
    channel = _channels_with_counts().get(pk=channel.pk)

    if request.headers.get("HX-Request"):
        oob_swap = (
            "afterbegin:#channel-list"
            if created
            else f"outerHTML:#channel-{channel.id}"
        )
        resp = render(request, "channels/_add_channel_success.html", {
            "channel": channel,
            "form": AddChannelForm(),
            "oob_swap": oob_swap,
        })
        resp["HX-Trigger"] = json.dumps({
            "atva:channelSaved": {"created": created},
        })
        return resp

    if is_ajax:
        return JsonResponse({
            "row_html": render_to_string("channels/_channel_row.html", {"channel": channel}, request=request),
            "form_html": render_to_string("channels/_add_form.html", {"form": AddChannelForm()}, request=request),
            "created": created,
        })

    return render(request, "channels/index.html", {
        "channels": Channel.objects.all(),
        "form": AddChannelForm(),
    })


@require_POST
def sync_channel(request, channel_id):
    """POST /channels/<id>/sync/ — manually trigger re-sync."""
    channel = get_object_or_404(Channel, pk=channel_id)
    discover_channel_videos.delay(str(channel.id))
    if request.headers.get("HX-Request") or request.headers.get("X-Atva-Ajax") == "1":
        resp = HttpResponse('<span class="text-green-600">Sync triggered</span>')
        resp["HX-Trigger"] = json.dumps({
            "atva:syncTriggered": {"channel_id": str(channel.id)},
        })
        return resp
    return render(request, "channels/index.html", {
        "channels": Channel.objects.all(),
        "form": AddChannelForm(),
    })


@require_POST
def summarize_channel(request, channel_id):
    """POST /channels/<id>/summarize/ — summarize all unsummarized DONE videos."""
    channel = get_object_or_404(Channel, pk=channel_id)

    unsummarized_count = (
        Video.objects.filter(
            channel=channel,
            status=Video.Status.DONE,
            gcs_prefix__gt="",
        )
        .exclude(artifacts__type=Artifact.ArtifactType.SUMMARY_MD)
        .count()
    )

    if unsummarized_count == 0:
        if request.headers.get("HX-Request") or request.headers.get("X-Atva-Ajax") == "1":
            return HttpResponse('<span class="text-yellow-600">No videos to summarize</span>')
        return render(request, "channels/index.html", {
            "channels": _channels_with_counts().order_by("-created_at"),
            "form": AddChannelForm(),
        })

    summarize_channel_videos.delay(str(channel.id))

    if request.headers.get("HX-Request") or request.headers.get("X-Atva-Ajax") == "1":
        msg = f'<span class="text-green-600">Summarizing {unsummarized_count} video(s)</span>'
        resp = HttpResponse(msg)
        resp["HX-Trigger"] = json.dumps({
            "atva:summarizeTriggered": {"channel_id": str(channel.id)},
        })
        return resp
    return render(request, "channels/index.html", {
        "channels": _channels_with_counts().order_by("-created_at"),
        "form": AddChannelForm(),
    })


def export_channel_pdf(request, channel_id):
    """GET /channels/<id>/export/?type=transcript|summary — download collated PDF."""
    channel = get_object_or_404(Channel, pk=channel_id)
    export_type = request.GET.get("type", "")

    if export_type not in ("transcript", "summary"):
        return HttpResponse("Invalid export type. Use ?type=transcript or ?type=summary", status=400)

    videos_qs = Video.objects.filter(
        channel=channel,
        status=Video.Status.DONE,
    ).order_by("published_at")

    if export_type == "transcript":
        videos_qs = videos_qs.filter(
            artifacts__type__in=[
                Artifact.ArtifactType.TRANSCRIPT_JSON,
                Artifact.ArtifactType.TRANSCRIPT_TXT,
            ]
        ).distinct()
    else:
        videos_qs = videos_qs.filter(
            artifacts__type=Artifact.ArtifactType.SUMMARY_MD,
        ).distinct()

    loader = load_transcript if export_type == "transcript" else load_summary
    videos_with_data = []
    for video in videos_qs:
        data = loader(video)
        if data:
            videos_with_data.append((video, data))

    if not videos_with_data:
        label = "transcripts" if export_type == "transcript" else "summaries"
        msg = f"No {label} available for this channel."
        if request.headers.get("HX-Request"):
            return HttpResponse(f'<span class="text-yellow-600">{msg}</span>')
        return HttpResponse(msg, status=404)

    buf = build_channel_pdf(channel, export_type, videos_with_data)

    safe_title = re.sub(r"[^\w\s-]", "", channel.title or "channel").strip().replace(" ", "_")
    filename = f"{safe_title}_{export_type}s.pdf"

    response = HttpResponse(buf.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
