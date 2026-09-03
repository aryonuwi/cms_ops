"""Operational endpoints that belong to no single feature."""

from django.db import connections
from django.db.utils import OperationalError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache


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
