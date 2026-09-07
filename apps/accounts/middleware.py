"""Middleware to enforce 2FA verification before accessing Django admin."""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from . import selectors


class TwoFactorVerificationMiddleware:
    """Enforce 2FA verification for authenticated staff users visiting the admin.

    If a user has 2FA enabled and their current session has not completed TOTP
    verification, redirects all admin requests to the 2FA verify view.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        admin_prefix = "/" + getattr(settings, "ADMIN_URL", "admin/").lstrip("/")
        path = request.path

        if path.startswith(admin_prefix) and request.user.is_authenticated and request.user.is_staff:
            verify_url = reverse("accounts:two_factor_verify")
            logout_url = f"{admin_prefix}logout/"
            setup_url = reverse("accounts:two_factor_setup")

            # Allow verify view, setup view, and logout
            if path not in (verify_url, logout_url, setup_url):
                if selectors.is_two_factor_enabled(request.user):
                    if not request.session.get("two_factor_verified"):
                        return redirect(f"{verify_url}?next={path}")

        return self.get_response(request)
