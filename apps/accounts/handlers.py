"""Subscriptions to other modules' events.

Wired from `AccountsConfig.ready()`. Keeping them here means a module never
reaches into another module's internals - it only reacts to published facts.
"""

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from apps.common import events as bus

from . import selectors, services
from .models import UserActivity


def _request_context(request) -> tuple[str | None, str]:
    """Extract audit metadata while keeping request objects out of services."""
    if request is None:
        return None, ""
    return request.META.get("REMOTE_ADDR"), request.META.get("HTTP_USER_AGENT", "")


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    ip_address, user_agent = _request_context(request)
    services.record_activity(
        user_id=user.pk,
        actor_id=user.pk,
        action=UserActivity.Action.LOGIN_SUCCESS,
        description="Login berhasil.",
        ip_address=ip_address,
        user_agent=user_agent,
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    ip_address, user_agent = _request_context(request)
    services.record_activity(
        user_id=user.pk if user is not None else None,
        actor_id=user.pk if user is not None else None,
        action=UserActivity.Action.LOGOUT,
        description="Logout.",
        ip_address=ip_address,
        user_agent=user_agent,
    )


@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    email = credentials.get("email") or credentials.get("username")
    user = selectors.get_user_by_email(email) if email else None
    ip_address, user_agent = _request_context(request)
    services.record_activity(
        user_id=user.pk if user is not None else None,
        action=UserActivity.Action.LOGIN_FAILED,
        description="Percobaan login gagal.",
        ip_address=ip_address,
        user_agent=user_agent,
    )


def register_subscriptions() -> None:
    # Example:
    #   bus.subscribe("billing.subscription_cancelled", _on_subscription_cancelled)
    pass


register_subscriptions()

__all__ = ["register_subscriptions", "bus"]
