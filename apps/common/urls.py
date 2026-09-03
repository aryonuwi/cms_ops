from django.urls import path

from . import views

app_name = "common"

urlpatterns = [
    path("live/", views.liveness, name="liveness"),
    path("ready/", views.readiness, name="readiness"),
]
