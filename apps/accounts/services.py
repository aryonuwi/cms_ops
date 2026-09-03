"""Write-side API of the accounts module.

Every state change goes through here so validation, transactions and event
publication stay in one place - never in a view, admin or another module.
"""

from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from apps.common.events import publish

from . import events, selectors
from .models import User


@transaction.atomic
def register_user(*, email: str, password: str, **extra) -> User:
    """Create an operator account and announce it."""
    email = email.strip().lower()

    # Validate against the configured policy before the hash is computed.
    validate_password(password, User(email=email))

    user = User.objects.create_user(email=email, password=password, **extra)

    transaction.on_commit(
        lambda: publish(events.user_registered(user_id=user.pk, email=user.email))
    )
    return user


@transaction.atomic
def update_user(
    *,
    user: User,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
) -> User:
    """Change only the profile fields that were provided.

    ``None`` means "leave it alone", so callers never need to know the current
    value to update a single field. The email is normalised here as a first
    pass; ``User.save()`` normalises again as the final guard.
    """
    update_fields: list[str] = []

    if first_name is not None:
        user.first_name = first_name
        update_fields.append("first_name")
    if last_name is not None:
        user.last_name = last_name
        update_fields.append("last_name")
    if email is not None:
        email = email.strip().lower()
        if email != user.email:
            if selectors.get_user_by_email(email) is not None:
                raise ValueError("Email address is already in use.")
            user.email = email
            update_fields.append("email")

    if not update_fields:
        return user

    user.save(update_fields=update_fields)

    transaction.on_commit(lambda: publish(events.user_updated(user_id=user.pk)))
    return user


@transaction.atomic
def activate_user(*, user: User) -> User:
    """Re-enable sign-in by moving the account status to ACTIVE."""
    if user.status == User.Status.ACTIVE:
        return user

    user.status = User.Status.ACTIVE
    user.save(update_fields=["status"])

    transaction.on_commit(lambda: publish(events.user_activated(user_id=user.pk)))
    return user


@transaction.atomic
def suspend_user(*, user: User) -> User:
    """Temporarily block sign-in without touching the account's history."""
    if user.status == User.Status.SUSPENDED:
        return user

    user.status = User.Status.SUSPENDED
    user.save(update_fields=["status"])

    transaction.on_commit(lambda: publish(events.user_suspended(user_id=user.pk)))
    return user


@transaction.atomic
def deactivate_user(*, user: User) -> User:
    """Disable sign-in without deleting history.

    Rows are kept rather than deleted so audit trails and foreign keys in other
    modules stay intact. ``status`` is the source of truth; ``is_active``
    follows from it in ``User.save()``.
    """
    if user.status == User.Status.INACTIVE:
        return user

    user.status = User.Status.INACTIVE
    user.save(update_fields=["status"])

    transaction.on_commit(lambda: publish(events.user_deactivated(user_id=user.pk)))
    return user


@transaction.atomic
def assign_group(*, user: User, group: Group) -> User:
    """Add the user to a group once, announcing only a real change."""
    if user.groups.filter(pk=group.pk).exists():
        return user

    user.groups.add(group)

    transaction.on_commit(
        lambda: publish(events.group_assigned(user_id=user.pk, group_id=group.pk))
    )
    return user


@transaction.atomic
def unassign_group(*, user: User, group: Group) -> User:
    """Remove the user from a group once, announcing only a real change."""
    if not user.groups.filter(pk=group.pk).exists():
        return user

    user.groups.remove(group)

    transaction.on_commit(
        lambda: publish(events.group_unassigned(user_id=user.pk, group_id=group.pk))
    )
    return user


@transaction.atomic
def grant_permission(*, user: User, permission: Permission) -> User:
    """Grant a personal permission once, announcing only a real change."""
    if user.user_permissions.filter(pk=permission.pk).exists():
        return user

    user.user_permissions.add(permission)

    transaction.on_commit(
        lambda: publish(
            events.permission_granted(
                user_id=user.pk, permission_codename=permission.codename
            )
        )
    )
    return user


@transaction.atomic
def revoke_permission(*, user: User, permission: Permission) -> User:
    """Revoke a personal permission once, announcing only a real change."""
    if not user.user_permissions.filter(pk=permission.pk).exists():
        return user

    user.user_permissions.remove(permission)

    transaction.on_commit(
        lambda: publish(
            events.permission_revoked(
                user_id=user.pk, permission_codename=permission.codename
            )
        )
    )
    return user


@transaction.atomic
def change_password(*, user: User, new_password: str) -> User:
    validate_password(new_password, user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    return user
