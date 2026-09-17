"""The project's user model.

Declared before the first migration on purpose: swapping AUTH_USER_MODEL after
tables exist requires a manual data migration across every FK in the project.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel, UUIDPrimaryKeyModel


class UserManager(BaseUserManager):
    """Manager keyed on email rather than a separate username."""

    use_in_migrations = True

    def get_queryset(self):
        qs = super().get_queryset()
        if any(f.name == "is_deleted" for f in self.model._meta.get_fields()):
            return qs.filter(is_deleted=False)
        return qs

    def all_with_deleted(self):
        return super().get_queryset()

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        # An explicit is_active=False at create time must survive the save()
        # invariant (which derives is_active from status) - otherwise a
        # deactivated account would silently come back active.
        if user.is_active is False:
            user.status = user.Status.INACTIVE
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)

        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra)


class User(UUIDPrimaryKeyModel, AbstractUser):
    """Authenticated operator.

    `username` is dropped in favour of a unique, case-normalised email.
    """

    class Status(models.IntegerChoices):
        """Account lifecycle value + meaning.

        0 = INACTIVE (permanently disabled), 1 = ACTIVE, 2 = SUSPENDED
        (temporarily disabled). INACTIVE and SUSPENDED both block sign-in.
        """

        INACTIVE = 0, _("inactive")
        ACTIVE = 1, _("active")
        SUSPENDED = 2, _("suspended")

    username = None
    email = models.EmailField(_("email address"), unique=True, db_index=True)
    status = models.IntegerField(
        _("status"), choices=Status.choices, default=Status.ACTIVE
    )

    # Audit trail (who and when)
    created_at = models.DateTimeField(
        _("created at"), default=timezone.now, db_index=True
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by_id = models.UUIDField(
        _("created by id"), null=True, blank=True, editable=False, db_index=True
    )
    updated_by_id = models.UUIDField(
        _("updated by id"), null=True, blank=True, editable=False
    )

    # Soft-delete primitives (no permanent data deletion via the system)
    is_deleted = models.BooleanField(
        _("is deleted"), default=False, db_index=True, editable=False
    )
    deleted_at = models.DateTimeField(
        _("deleted at"), null=True, blank=True, editable=False
    )
    deleted_by_id = models.UUIDField(
        _("deleted by id"), null=True, blank=True, editable=False
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["email"]

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.__class__.objects.normalize_email(self.email).lower()
        # `status` is the source of truth; `is_active` is derived here in one
        # place so Django's ModelBackend keeps gating sign-in without a custom
        # auth backend.
        self.is_active = (self.status == self.Status.ACTIVE) and (not self.is_deleted)
        # A targeted update of `status` alone would leave the derived
        # `is_active` stale in the database, so it is pulled into the write.
        if (
            "update_fields" in kwargs
            and "status" in kwargs["update_fields"]
            and "is_active" not in kwargs["update_fields"]
        ):
            kwargs["update_fields"] = [*kwargs["update_fields"], "is_active"]
        return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False, *, deleted_by_id=None):
        """Soft-delete the user account rather than permanently deleting the row."""
        self.is_deleted = True
        self.status = self.Status.INACTIVE
        self.is_active = False
        self.deleted_at = timezone.now()
        if deleted_by_id is not None:
            self.deleted_by_id = deleted_by_id
        update_fields = [
            "is_deleted",
            "status",
            "is_active",
            "deleted_at",
            "deleted_by_id",
            "updated_at",
        ]
        self.save(update_fields=update_fields)

    def hard_delete(self, using=None, keep_parents=False):
        """Physical deletion, restricted from normal operational flows."""
        return super().delete(using=using, keep_parents=keep_parents)


class UserTwoFactor(BaseModel):
    """Stores symmetrically encrypted TOTP secret for Google Authenticator.

    Keyed by user_id (UUIDField, R4-clean).
    The secret is encrypted with dynamic per-user key derivation (HKDF-SHA256).
    """

    user_id = models.UUIDField(_("user id"), unique=True, db_index=True)
    encrypted_secret = models.BinaryField(_("encrypted secret"))
    is_enabled = models.BooleanField(_("is enabled"), default=False)

    class Meta:
        verbose_name = _("user two factor")
        verbose_name_plural = _("user two factors")

    def __str__(self) -> str:
        status_str = "enabled" if self.is_enabled else "pending"
        return f"2FA({self.user_id}): {status_str}"


class UserActivity(BaseModel):
    """Immutable-style security and account activity for operators.

    ``user_id`` and ``actor_id`` stay as UUIDs rather than foreign keys so the
    accounts module can be split without coupling its audit table to another
    module's database. Passwords and reset tokens are deliberately never
    stored in ``details``.
    """

    class Action(models.TextChoices):
        USER_CREATED = "user_created", _("User dibuat")
        USER_UPDATED = "user_updated", _("Profil user diperbarui")
        USER_DELETED = "user_deleted", _("User dinonaktifkan")
        PASSWORD_CHANGED = "password_changed", _("Password diubah")
        PASSWORD_RESET_REQUESTED = "password_reset_requested", _(
            "Link reset password dikirim"
        )
        PASSWORD_RESET_COMPLETED = "password_reset_completed", _(
            "Password di-reset melalui link"
        )
        USER_ACTIVATED = "user_activated", _("User diaktifkan")
        USER_SUSPENDED = "user_suspended", _("User ditangguhkan")
        USER_DEACTIVATED = "user_deactivated", _("User dinonaktifkan")
        GROUP_ASSIGNED = "group_assigned", _("Group ditambahkan")
        GROUP_UNASSIGNED = "group_unassigned", _("Group dihapus")
        PERMISSION_GRANTED = "permission_granted", _("Permission diberikan")
        PERMISSION_REVOKED = "permission_revoked", _("Permission dicabut")
        TWO_FACTOR_SETUP = "two_factor_setup", _("Setup 2FA dimulai")
        TWO_FACTOR_ENABLED = "two_factor_enabled", _("2FA diaktifkan")
        TWO_FACTOR_DISABLED = "two_factor_disabled", _("2FA di-reset")
        LOGIN_SUCCESS = "login_success", _("Login berhasil")
        LOGIN_FAILED = "login_failed", _("Login gagal")
        LOGOUT = "logout", _("Logout")

    user_id = models.UUIDField(
        _("user id"), null=True, blank=True, db_index=True
    )
    actor_id = models.UUIDField(
        _("actor id"), null=True, blank=True, db_index=True
    )
    action = models.CharField(
        _("action"), max_length=64, choices=Action.choices, db_index=True
    )
    description = models.CharField(_("description"), max_length=255, blank=True)
    details = models.JSONField(_("details"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(
        _("IP address"), null=True, blank=True
    )
    user_agent = models.TextField(_("user agent"), blank=True)

    class Meta:
        verbose_name = _("user activity")
        verbose_name_plural = _("user activities")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action}({self.user_id})"
