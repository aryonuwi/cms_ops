"""URLs for accounts module."""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path(
        "password-reset/<uidb64>/<token>/",
        views.password_reset_confirm_view,
        name="password_reset_confirm",
    ),
    path("2fa/verify/", views.two_factor_verify_view, name="two_factor_verify"),
    path("2fa/setup/", views.two_factor_setup_view, name="two_factor_setup"),
]
