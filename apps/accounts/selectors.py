"""Read-side API of the accounts module.

Other modules call these functions instead of importing `accounts.models`.
When accounts becomes its own service, this file is what turns into an HTTP or
gRPC client - callers do not change.
"""

from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.db.models import QuerySet

from .models import User


def get_user_by_id(user_id) -> User | None:
    return User.objects.filter(pk=user_id).first()


def get_user_by_email(email: str) -> User | None:
    return User.objects.filter(email__iexact=email.strip()).first()


def list_active_users() -> QuerySet[User]:
    return User.objects.filter(is_active=True)


def list_staff_users() -> QuerySet[User]:
    return User.objects.filter(is_active=True, is_staff=True)


def list_user_groups(user: User) -> QuerySet[Group]:
    """The user's groups, ordered by name for stable rendering."""
    return user.groups.all().order_by("name")


def get_user_permissions(user: User) -> set[str]:
    """Effective permissions in the ``app_label.codename`` shape.

    Mirrors Django's ``has_perm`` semantics so this read API can never drift
    from what the auth backend actually enforces: inactive users hold nothing,
    superusers hold every permission, everyone else holds the union of group
    and personal permissions.
    """
    if not user.is_active:
        return set()
    if user.is_superuser:
        return {
            f"{app_label}.{codename}"
            for app_label, codename in Permission.objects.values_list(
                "content_type__app_label", "codename"
            )
        }
    return set(user.get_all_permissions())


def count_active_superadmins() -> int:
    """Return count of active superuser accounts."""
    return User.objects.filter(is_superuser=True, is_active=True).count()


def is_two_factor_enabled(user: User) -> bool:
    """Check if 2FA (TOTP) is active for the given user."""
    from .models import UserTwoFactor

    return UserTwoFactor.objects.filter(user_id=user.pk, is_enabled=True).exists()


def get_user_two_factor(user: User):
    """Retrieve 2FA record for the given user if one exists."""
    from .models import UserTwoFactor

    return UserTwoFactor.objects.filter(user_id=user.pk).first()
