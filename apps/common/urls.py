from django.urls import path

from . import views

app_name = "common"

# Module ini dipasang di root (lihat config/urls.py), jadi prefix `health/`
# ditulis di sini - URL probe-nya tetap /health/live/ dan /health/ready/.
urlpatterns = [
    path("", views.home, name="home"),
    path("health/live/", views.liveness, name="liveness"),
    path("health/ready/", views.readiness, name="readiness"),
]
