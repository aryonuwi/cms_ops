"""Write-side API of the accounts module.

Every state change goes through here so validation, transactions and event
publication stay in one place - never in a view, admin or another module.
"""

from __future__ import annotations

import uuid

import pyotp
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.common import crypto
from apps.common.events import publish

from . import events, selectors
from .models import User, UserTwoFactor


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
    new_password: str | None = None,
    updated_by_id: uuid.UUID | None = None,
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
            existing = selectors.get_user_by_email(email)
            if existing is not None and existing.pk != user.pk:
                raise ValueError("Email address is already in use.")
            user.email = email
            update_fields.append("email")
    if new_password:
        validate_password(new_password, user)
        user.set_password(new_password)
        update_fields.append("password")
    if updated_by_id is not None:
        user.updated_by_id = updated_by_id
        update_fields.append("updated_by_id")

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


@transaction.atomic
def delete_user(*, user: User, requested_by: User | None = None) -> None:
    """Soft-delete a user account with superadmin protection.

    Enforces that:
    1. A superadmin cannot be deleted if active superadmin count <= 1.
    2. 'admin@ops.local' cannot be deleted unless another active superadmin exists.
    3. The record is soft-deleted, preserving audit history (no hard DELETE FROM).
    """
    if user.is_superuser:
        superadmin_count = selectors.count_active_superadmins()
        if superadmin_count <= 1:
            raise ValidationError("Akun superadmin terakhir tidak dapat dihapus demi keamanan sistem.")
        if user.email.lower() == "admin@ops.local" and superadmin_count <= 1:
            raise ValidationError("Akun admin@ops.local tidak dapat dihapus kecuali terdapat lebih dari satu superadmin.")

    user.delete(deleted_by_id=requested_by.pk if requested_by else None)

    transaction.on_commit(
        lambda: publish(events.user_deleted(user_id=user.pk, email=user.email))
    )


@transaction.atomic
def ensure_seed_superadmin() -> User:
    """Ensure admin@ops.local exists and holds active superadmin privileges."""
    admin_email = getattr(settings, "SEED_ADMIN_EMAIL", "admin@ops.local")
    admin_pw = getattr(settings, "SEED_ADMIN_PASSWORD", "OpsViews!Dev2026")

    user = selectors.get_user_by_email(admin_email)
    if user is None:
        user = register_user(
            email=admin_email,
            password=admin_pw,
            is_staff=True,
            is_superuser=True,
        )
    else:
        updated = False
        if not user.is_superuser:
            user.is_superuser = True
            updated = True
        if not user.is_staff:
            user.is_staff = True
            updated = True
        if user.status != User.Status.ACTIVE:
            user.status = User.Status.ACTIVE
            user.is_active = True
            updated = True
        if user.is_deleted:
            user.is_deleted = False
            user.deleted_at = None
            user.deleted_by_id = None
            updated = True
        if updated:
            user.save()
    return user


@transaction.atomic
def setup_two_factor(*, user: User) -> tuple[str, str]:
    """Generate a new TOTP secret for Google Authenticator.

    The secret is encrypted symmetrically with per-user key derivation (HKDF-SHA256)
    before being saved to the database. Returns (raw_secret, otpauth_uri).
    """
    secret = pyotp.random_base32()
    encrypted = crypto.encrypt_user_secret(
        plaintext=secret, user_id=user.pk, context=user.email
    )

    u2f, _created = UserTwoFactor.all_objects.update_or_create(
        user_id=user.pk,
        defaults={
            "encrypted_secret": encrypted,
            "is_enabled": False,
            "is_deleted": False,
            "deleted_at": None,
            "deleted_by_id": None,
        },
    )

    totp = pyotp.TOTP(secret)
    site_title = getattr(settings, "SITE_TITLE", "CMS Ops")
    uri = totp.provisioning_uri(name=user.email, issuer_name=site_title)

    transaction.on_commit(
        lambda: publish(events.two_factor_setup_initiated(user_id=user.pk))
    )
    return secret, uri


@transaction.atomic
def enable_two_factor(*, user: User, code: str) -> bool:
    """Verify code and activate 2FA for the user."""
    u2f = UserTwoFactor.all_objects.filter(user_id=user.pk, is_deleted=False).first()
    if u2f is None:
        return False

    try:
        secret = crypto.decrypt_user_secret(
            ciphertext=u2f.encrypted_secret, user_id=user.pk, context=user.email
        )
    except crypto.TamperDetectedError:
        u2f.is_enabled = False
        u2f.delete()
        transaction.on_commit(
            lambda: publish(events.two_factor_tampered_reset(user_id=user.pk))
        )
        return False

    totp = pyotp.TOTP(secret)
    if totp.verify(code.strip(), valid_window=1):
        u2f.is_enabled = True
        u2f.save(update_fields=["is_enabled", "updated_at"])
        transaction.on_commit(
            lambda: publish(events.two_factor_enabled(user_id=user.pk))
        )
        return True
    return False


@transaction.atomic
def disable_two_factor(*, user: User, requested_by: User | None = None) -> None:
    """Disable 2FA for the user and soft-delete the TOTP record."""
    u2f = UserTwoFactor.objects.filter(user_id=user.pk).first()
    if u2f is not None:
        u2f.is_enabled = False
        u2f.delete(deleted_by_id=requested_by.pk if requested_by else None)
        transaction.on_commit(
            lambda: publish(events.two_factor_disabled(user_id=user.pk))
        )


@transaction.atomic
def verify_two_factor_code(*, user: User, code: str) -> bool:
    """Verify a 6-digit TOTP code against the encrypted secret in the database.

    If database tampering is detected during decryption, automatically resets
    2FA (is_enabled=False) and returns False to protect the account.
    """
    u2f = UserTwoFactor.objects.filter(user_id=user.pk, is_enabled=True).first()
    if u2f is None:
        return False

    try:
        secret = crypto.decrypt_user_secret(
            ciphertext=u2f.encrypted_secret, user_id=user.pk, context=user.email
        )
    except crypto.TamperDetectedError:
        # Automatic reset when manual tampering or database corruption is detected!
        u2f.is_enabled = False
        u2f.delete()
        transaction.on_commit(
            lambda: publish(events.two_factor_tampered_reset(user_id=user.pk))
        )
        return False

    totp = pyotp.TOTP(secret)
    return bool(totp.verify(code.strip(), valid_window=1))
