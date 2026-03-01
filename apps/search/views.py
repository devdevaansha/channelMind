import logging

from django.shortcuts import render

from apps.channels.models import Category, Channel, Video

logger = logging.getLogger(__name__)


def search_view(request):
    """Tab 4: Semantic search via Pinecone embeddings."""
    query = request.GET.get("q", "").strip()
    channel_id = request.GET.get("channel", "")
    category_id = request.GET.get("category", "")
    result_type = request.GET.get("type", "")  # transcript / summary
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    results = []
    error = None

    if query and len(query) >= 3:
        try:
            from services.pinecone_client import PineconeClient

            pc = PineconeClient()

            # Embed the query via Pinecone Inference
            query_vector = pc.embed_texts([query], input_type="query")[0]

            # Build Pinecone metadata filter
            pc_filter: dict = {}
            if channel_id:
                pc_filter["channel_id"] = {"$eq": channel_id}
            if category_id:
                pc_filter["category_id"] = {"$eq": category_id}
            if result_type:
                pc_filter["type"] = {"$eq": result_type}

            matches = pc.query(
                vector=query_vector,
                top_k=10,
                filter=pc_filter if pc_filter else None,
            )

            # Hydrate with DB video objects
            video_ids = list({m["metadata"].get("video_id", "") for m in matches})
            videos_by_id = {
                str(v.id): v
                for v in Video.objects.filter(pk__in=video_ids).select_related("channel", "category")
            }

            for match in matches:
                meta = match.get("metadata", {})
                vid = videos_by_id.get(meta.get("video_id", ""))
                results.append({
                    "score": round(match.get("score", 0), 4),
                    "text": meta.get("text", ""),
                    "source": meta.get("source", ""),
                    "start": meta.get("start"),
                    "end": meta.get("end"),
                    "video": vid,
                })

        except Exception as e:
            logger.exception("Search failed: %s", e)
            error = str(e)
    elif query:
        # Avoid expensive remote calls for very short queries.
        results = []
        error = None

    ctx = {
        "query": query,
        "results": results,
        "error": error,
        "channels": Channel.objects.all(),
        "categories": Category.objects.all(),
        "selected_channel": channel_id,
        "selected_category": category_id,
        "selected_type": result_type,
    }

    if request.headers.get("HX-Request"):
        return render(request, "search/_result_item.html", ctx)
    return render(request, "search/index.html", ctx)
