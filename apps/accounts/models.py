"""The project's user model.

Declared before the first migration on purpose: swapping AUTH_USER_MODEL after
tables exist requires a manual data migration across every FK in the project.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import UUIDPrimaryKeyModel


class UserManager(BaseUserManager):
    """Manager keyed on email rather than a separate username."""

    use_in_migrations = True

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

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

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
        self.is_active = self.status == self.Status.ACTIVE
        # A targeted update of `status` alone would leave the derived
        # `is_active` stale in the database, so it is pulled into the write.
        if (
            "update_fields" in kwargs
            and "status" in kwargs["update_fields"]
            and "is_active" not in kwargs["update_fields"]
        ):
            kwargs["update_fields"] = [*kwargs["update_fields"], "is_active"]
        return super().save(*args, **kwargs)
