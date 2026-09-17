"""Write-side API of the accounts module.

Every state change goes through here so validation, transactions and event
publication stay in one place - never in a view, admin or another module.
"""

from __future__ import annotations

import uuid

import pyotp
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _

from apps.common import crypto
from apps.common.events import publish

from . import events, selectors
from .models import User, UserActivity, UserTwoFactor


@transaction.atomic
def record_activity(
    *,
    action: str,
    user_id=None,
    actor_id=None,
    description: str = "",
    details: dict | None = None,
    ip_address: str | None = None,
    user_agent: str = "",
) -> UserActivity:
    """Persist an audit row without ever accepting secrets or tokens."""
    return UserActivity.objects.create(
        user_id=user_id,
        actor_id=actor_id,
        action=action,
        description=description[:255],
        details=details or {},
        ip_address=ip_address,
        user_agent=user_agent[:1000],
        created_by_id=actor_id,
        updated_by_id=actor_id,
    )


@transaction.atomic
def register_user(*, email: str, password: str, **extra) -> User:
    """Create an operator account and announce it."""
    email = email.strip().lower()

    # Validate against the configured policy before the hash is computed.
    validate_password(password, User(email=email))

    user = User.objects.create_user(email=email, password=password, **extra)

    record_activity(
        user_id=user.pk,
        actor_id=extra.get("created_by_id"),
        action=UserActivity.Action.USER_CREATED,
        description="Akun user dibuat.",
    )

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
    changed_profile_fields: list[str] = []
    password_changed = False

    if first_name is not None and first_name != user.first_name:
        user.first_name = first_name
        update_fields.append("first_name")
        changed_profile_fields.append("first_name")
    if last_name is not None and last_name != user.last_name:
        user.last_name = last_name
        update_fields.append("last_name")
        changed_profile_fields.append("last_name")
    if email is not None:
        email = email.strip().lower()
        if email != user.email:
            existing = selectors.get_user_by_email(email)
            if existing is not None and existing.pk != user.pk:
                raise ValueError("Email address is already in use.")
            user.email = email
            update_fields.append("email")
            changed_profile_fields.append("email")
    if new_password:
        validate_password(new_password, user)
        user.set_password(new_password)
        update_fields.append("password")
        password_changed = True
    if updated_by_id is not None:
        user.updated_by_id = updated_by_id
        update_fields.append("updated_by_id")

    if not update_fields:
        return user

    user.save(update_fields=update_fields)

    if changed_profile_fields:
        record_activity(
            user_id=user.pk,
            actor_id=updated_by_id,
            action=UserActivity.Action.USER_UPDATED,
            description="Profil user diperbarui.",
            details={"fields": changed_profile_fields},
        )
    if password_changed:
        record_activity(
            user_id=user.pk,
            actor_id=updated_by_id,
            action=UserActivity.Action.PASSWORD_CHANGED,
            description="Password diubah langsung oleh admin.",
        )

    transaction.on_commit(lambda: publish(events.user_updated(user_id=user.pk)))
    return user


@transaction.atomic
def activate_user(*, user: User, requested_by_id=None) -> User:
    """Re-enable sign-in by moving the account status to ACTIVE."""
    if user.status == User.Status.ACTIVE:
        return user

    user.status = User.Status.ACTIVE
    user.save(update_fields=["status"])

    record_activity(
        user_id=user.pk,
        actor_id=requested_by_id,
        action=UserActivity.Action.USER_ACTIVATED,
        description="User diaktifkan.",
    )

    transaction.on_commit(lambda: publish(events.user_activated(user_id=user.pk)))
    return user


@transaction.atomic
def suspend_user(*, user: User, requested_by_id=None) -> User:
    """Temporarily block sign-in without touching the account's history."""
    if user.status == User.Status.SUSPENDED:
        return user

    user.status = User.Status.SUSPENDED
    user.save(update_fields=["status"])

    record_activity(
        user_id=user.pk,
        actor_id=requested_by_id,
        action=UserActivity.Action.USER_SUSPENDED,
        description="User ditangguhkan.",
    )

    transaction.on_commit(lambda: publish(events.user_suspended(user_id=user.pk)))
    return user


@transaction.atomic
def deactivate_user(*, user: User, requested_by_id=None) -> User:
    """Disable sign-in without deleting history.

    Rows are kept rather than deleted so audit trails and foreign keys in other
    modules stay intact. ``status`` is the source of truth; ``is_active``
    follows from it in ``User.save()``.
    """
    if user.status == User.Status.INACTIVE:
        return user

    user.status = User.Status.INACTIVE
    user.save(update_fields=["status"])

    record_activity(
        user_id=user.pk,
        actor_id=requested_by_id,
        action=UserActivity.Action.USER_DEACTIVATED,
        description="User dinonaktifkan.",
    )

    transaction.on_commit(lambda: publish(events.user_deactivated(user_id=user.pk)))
    return user


@transaction.atomic
def assign_group(*, user: User, group: Group, requested_by_id=None) -> User:
    """Add the user to a group once, announcing only a real change."""
    if user.groups.filter(pk=group.pk).exists():
        return user

    user.groups.add(group)

    record_activity(
        user_id=user.pk,
        actor_id=requested_by_id,
        action=UserActivity.Action.GROUP_ASSIGNED,
        description=f"Group {group.name} ditambahkan.",
        details={"group_id": str(group.pk)},
    )

    transaction.on_commit(
        lambda: publish(events.group_assigned(user_id=user.pk, group_id=group.pk))
    )
    return user


@transaction.atomic
def unassign_group(*, user: User, group: Group, requested_by_id=None) -> User:
    """Remove the user from a group once, announcing only a real change."""
    if not user.groups.filter(pk=group.pk).exists():
        return user

    user.groups.remove(group)

    record_activity(
        user_id=user.pk,
        actor_id=requested_by_id,
        action=UserActivity.Action.GROUP_UNASSIGNED,
        description=f"Group {group.name} dihapus.",
        details={"group_id": str(group.pk)},
    )

    transaction.on_commit(
        lambda: publish(events.group_unassigned(user_id=user.pk, group_id=group.pk))
    )
    return user


@transaction.atomic
def grant_permission(*, user: User, permission: Permission, requested_by_id=None) -> User:
    """Grant a personal permission once, announcing only a real change."""
    if user.user_permissions.filter(pk=permission.pk).exists():
        return user

    user.user_permissions.add(permission)

    record_activity(
        user_id=user.pk,
        actor_id=requested_by_id,
        action=UserActivity.Action.PERMISSION_GRANTED,
        description=f"Permission {permission.codename} diberikan.",
        details={"permission_id": permission.pk, "permission": permission.codename},
    )

    transaction.on_commit(
        lambda: publish(
            events.permission_granted(
                user_id=user.pk, permission_codename=permission.codename
            )
        )
    )
    return user


@transaction.atomic
def revoke_permission(*, user: User, permission: Permission, requested_by_id=None) -> User:
    """Revoke a personal permission once, announcing only a real change."""
    if not user.user_permissions.filter(pk=permission.pk).exists():
        return user

    user.user_permissions.remove(permission)

    record_activity(
        user_id=user.pk,
        actor_id=requested_by_id,
        action=UserActivity.Action.PERMISSION_REVOKED,
        description=f"Permission {permission.codename} dicabut.",
        details={"permission_id": permission.pk, "permission": permission.codename},
    )

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
    record_activity(
        user_id=user.pk,
        actor_id=user.pk,
        action=UserActivity.Action.PASSWORD_CHANGED,
        description="Password diubah oleh user.",
    )
    return user


@transaction.atomic
def send_password_reset_link(
    *,
    user: User,
    site_url: str,
    requested_by_id=None,
    ip_address: str | None = None,
    user_agent: str = "",
) -> str:
    """Email a short-lived reset URL without exposing a password to admins."""
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_path = reverse(
        "accounts:password_reset_confirm",
        kwargs={"uidb64": uidb64, "token": token},
    )
    reset_url = f"{site_url.rstrip('/')}{reset_path}"

    send_mail(
        subject=_("Reset password akun CMS Ops"),
        message=(
            f"Halo,\n\n"
            f"Gunakan tautan berikut untuk membuat password baru untuk akun {user.email}:\n\n"
            f"{reset_url}\n\n"
            "Tautan ini memiliki masa berlaku terbatas dan hanya dapat digunakan sekali. "
            "Jika Anda tidak meminta reset password, abaikan email ini.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    record_activity(
        user_id=user.pk,
        actor_id=requested_by_id,
        action=UserActivity.Action.PASSWORD_RESET_REQUESTED,
        description="Link reset password dikirim melalui email.",
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return reset_url


@transaction.atomic
def reset_password_from_token(
    *,
    user: User,
    token: str,
    new_password: str,
) -> User:
    """Set a new password only while the emailed token is still valid."""
    if not default_token_generator.check_token(user, token):
        raise ValidationError("Tautan reset password tidak valid atau sudah kedaluwarsa.")

    validate_password(new_password, user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    record_activity(
        user_id=user.pk,
        actor_id=user.pk,
        action=UserActivity.Action.PASSWORD_RESET_COMPLETED,
        description="Password di-reset melalui link email.",
    )
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

    record_activity(
        user_id=user.pk,
        actor_id=requested_by.pk if requested_by else None,
        action=UserActivity.Action.USER_DELETED,
        description="User dinonaktifkan melalui soft-delete.",
    )

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
    record_activity(
        user_id=user.pk,
        actor_id=user.pk,
        action=UserActivity.Action.TWO_FACTOR_SETUP,
        description="Setup 2FA dimulai.",
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
        record_activity(
            user_id=user.pk,
            actor_id=user.pk,
            action=UserActivity.Action.TWO_FACTOR_ENABLED,
            description="2FA diaktifkan.",
        )
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
    record_activity(
        user_id=user.pk,
        actor_id=requested_by.pk if requested_by else user.pk,
        action=UserActivity.Action.TWO_FACTOR_DISABLED,
        description="2FA di-reset atau dinonaktifkan.",
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
