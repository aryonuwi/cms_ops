"""Access-control data: the feature (menu) catalog and who may reach what.

Grouping itself is Django's ``auth.Group`` - already wired to ``User.groups``
and ``has_perm``. This module owns the mapping from groups, or individual
users, to the menus each feature module declares in its ``navigation.py``.
"""

from django.contrib.auth.models import Group
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class Feature(BaseModel):
    """A menu or capability another module declares in its ``navigation.py``.

    The catalog is seeded from those code declarations (see
    ``services.sync_features``) so the sidebar keeps being assembled per module
    (ADR-007), while grants have a stable row to point at.
    """

    slug = models.SlugField(_("slug"), max_length=100, unique=True)
    label = models.CharField(_("label"), max_length=150)
    module = models.CharField(_("module"), max_length=100, blank=True)
    description = models.TextField(_("description"), blank=True)
    # Optional Django permission codename (e.g. "accounts.view_user"). When
    # set, visibility and enforcement must both agree - this stops a user from
    # seeing a menu the admin itself would reject with a 403. Deliberately
    # operator-managed: sync_features never touches it.
    required_permission = models.CharField(
        _("required permission"), max_length=255, blank=True
    )
    is_active = models.BooleanField(_("is active"), default=True)

    class Meta:
        verbose_name = _("feature")
        verbose_name_plural = _("features")
        ordering = ["module", "label"]

    def __str__(self) -> str:
        return self.slug


class FeatureGrant(BaseModel):
    """One access decision: which group or user may (or may not) use a feature.

    ``deny`` outranks ``allow`` at the same level and a personal (user) grant
    outranks group grants - ``selectors.user_can_access`` is the single place
    that precedence is decided, and it stays fail-closed by default.
    """

    class GranteeType(models.TextChoices):
        GROUP = "group", _("Group")
        USER = "user", _("User")

    class Effect(models.TextChoices):
        ALLOW = "allow", _("Allow")
        DENY = "deny", _("Deny")

    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
        related_name="grants",
        verbose_name=_("feature"),
    )
    grantee_type = models.CharField(
        _("grantee type"), max_length=10, choices=GranteeType.choices
    )
    # auth.Group is the shared auth framework, not a feature module - a real FK
    # mirrors User.groups and keeps referential integrity in this database.
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="feature_grants",
        verbose_name=_("group"),
    )
    # accounts.User belongs to another feature module, so R4 applies: store
    # the id, not a ForeignKey, keeping this module liftable off the shared DB.
    user_id = models.UUIDField(_("user id"), null=True, blank=True, db_index=True)
    effect = models.CharField(
        _("effect"), max_length=10, choices=Effect.choices, default=Effect.ALLOW
    )

    class Meta:
        verbose_name = _("feature grant")
        verbose_name_plural = _("feature grants")
        ordering = ["feature__slug", "grantee_type"]
        constraints = [
            # A grant points at exactly one grantee - enforced by the database
            # so no code path can produce a half-filled row.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        grantee_type="group",
                        group__isnull=False,
                        user_id__isnull=True,
                    )
                    | models.Q(
                        grantee_type="user",
                        user_id__isnull=False,
                        group__isnull=True,
                    )
                ),
                name="access_grant_exactly_one_grantee",
            ),
            # One decision per feature + grantee: re-granting goes through
            # services.grant_feature, which upserts instead of duplicating.
            models.UniqueConstraint(
                fields=["feature", "group"],
                condition=models.Q(grantee_type="group"),
                name="access_grant_unique_per_group",
            ),
            models.UniqueConstraint(
                fields=["feature", "user_id"],
                condition=models.Q(grantee_type="user"),
                name="access_grant_unique_per_user",
            ),
        ]

    def __str__(self) -> str:
        if self.grantee_type == self.GranteeType.GROUP:
            return f"{self.feature}: {self.group}"
        return f"{self.feature}: user {self.user_id}"
