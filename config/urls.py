from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView


def healthz(request):
    """Health check: verifies DB connectivity."""
    from django.db import connection
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    status = 200 if db_ok else 503
    return JsonResponse({"status": "ok" if db_ok else "degraded", "db": db_ok}, status=status)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthz, name="healthz"),
    path("channels/", include("apps.channels.urls", namespace="channels")),
    path("jobs/", include("apps.jobs.urls", namespace="jobs")),
    path("library/", include("apps.library.urls", namespace="library")),
    path("search/", include("apps.search.urls", namespace="search")),
    # Root → channels tab
    path("", RedirectView.as_view(pattern_name="channels:index"), name="root"),
]
