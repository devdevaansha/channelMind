import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

from apps.channels.models import Category, Channel, Video
from apps.library.loaders import load_transcript, load_summary

logger = logging.getLogger(__name__)


def index(request):
    """Tab 3: Library — filterable video list."""
    channel_id = request.GET.get("channel", "")
    category_id = request.GET.get("category", "")
    status = request.GET.get("status", "")
    page = request.GET.get("page", "1")

    videos_qs = (
        Video.objects.select_related("channel", "category")
        .only(
            "id",
            "title",
            "status",
            "published_at",
            "channel__id",
            "channel__title",
            "category__id",
            "category__name",
        )
        .order_by("-published_at")
    )

    if channel_id:
        videos_qs = videos_qs.filter(channel_id=channel_id)
    if category_id:
        videos_qs = videos_qs.filter(category_id=category_id)
    if status:
        videos_qs = videos_qs.filter(status=status)

    paginator = Paginator(videos_qs, 30)
    page_obj = paginator.get_page(page)

    ctx = {
        "videos": page_obj.object_list,
        "page_obj": page_obj,
        "channels": Channel.objects.only("id", "title").order_by("title"),
        "categories": Category.objects.only("id", "name").order_by("name"),
        "statuses": Video.Status.choices,
        "selected_channel": channel_id,
        "selected_category": category_id,
        "selected_status": status,
    }

    if request.headers.get("HX-Request"):
        return render(request, "library/_video_list.html", ctx)
    return render(request, "library/index.html", ctx)


def video_detail(request, video_id):
    """Video detail: transcript + summary viewer + category assignment."""
    video = get_object_or_404(
        Video.objects.select_related("channel", "category"),
        pk=video_id,
    )

    transcript = load_transcript(video)
    summary = load_summary(video)

    return render(request, "library/detail.html", {
        "video": video,
        "transcript": transcript,
        "summary": summary,
        "categories": Category.objects.all(),
    })


@require_POST
def assign_category(request, video_id):
    """HTMX POST: assign a category to a video."""
    video = get_object_or_404(Video, pk=video_id)
    category_id = request.POST.get("category_id")
    if category_id:
        video.category_id = category_id
        video.save(update_fields=["category_id"])
    else:
        video.category = None
        video.save(update_fields=["category_id"])

    if request.headers.get("HX-Request"):
        return HttpResponse(f'<span class="text-green-600">Category updated</span>')

    return video_detail(request, video_id)
