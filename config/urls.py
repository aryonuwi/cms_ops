"""Root URL configuration.

Each feature module owns a `urls.py` and is mounted under its own prefix, so a
module can later be routed to a separate service by changing one line here (or
by removing it and pointing the gateway elsewhere).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    # Operational probes - no feature module owns these.
    path("health/", include("apps.common.urls")),
    # Feature modules
    # path("api/accounts/", include("apps.accounts.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
