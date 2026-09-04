"""Public entry point and operational endpoints that belong to no feature."""

from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache


def home(request: HttpRequest) -> HttpResponse:
    """Landing page at the site root.

    Public on purpose: it carries no operational data, only the way in. It also
    gives the admin's "return to site" link somewhere real to point - before it
    existed, that link led to a 404. Lives in `common` because no feature module
    owns the root, and it must stay that way (R7: common depends on nobody).
    """
    return render(request, "common/home.html", {"site_title": settings.SITE_TITLE})


@never_cache
def liveness(request: HttpRequest) -> JsonResponse:
    """Is the process up? Used by the container/orchestrator restart probe."""
    return JsonResponse({"status": "ok"})


@never_cache
def readiness(request: HttpRequest) -> JsonResponse:
    """Can the process serve traffic? Checks every configured database."""
    checks: dict[str, str] = {}
    healthy = True

    for alias in connections:
        try:
            with connections[alias].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks[f"database:{alias}"] = "ok"
        except OperationalError as exc:
            healthy = False
            checks[f"database:{alias}"] = f"error: {exc.__class__.__name__}"

    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status=200 if healthy else 503,
    )
