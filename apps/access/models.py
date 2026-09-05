"""Access-control data: the feature (menu) catalog and who may reach what.

Grouping itself is Django's ``auth.Group`` - already wired to ``User.groups``
and ``has_perm``. This module owns the mapping from groups, or individual
users, to the menus each feature module declares in its ``navigation.py``.
"""

from django.contrib.auth.models import Group
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class Module(BaseModel):
    """An installed feature module (a Django app under ``apps.*``).

    The top level of the access catalog. Seeded by ``services.sync_catalog``
    from the app registry, so adding a module records it here without editing a
    central list (ADR-007). Operators may deactivate a module they do not want
    surfaced; sync never deletes a module that disappeared from code.
    """

    slug = models.SlugField(_("slug"), max_length=100, unique=True)
    label = models.CharField(_("label"), max_length=150)
    package = models.CharField(_("package"), max_length=200, blank=True)
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("is active"), default=True)
    order = models.IntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("module")
        verbose_name_plural = _("modules")
        ordering = ["order", "slug"]

    def __str__(self) -> str:
        return self.slug


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


class Action(BaseModel):
    """A single function inside a feature, e.g. ``accounts.users.create``.

    Actions are the level grants point at when staff may only create while a
    supervisor may also edit. The ``slug`` is globally unique and prefixes the
    feature slug, so a dotted ``CharField`` is used on purpose - a ``SlugField``
    would reject the separator.
    """

    class Category(models.TextChoices):
        CREATE = "create", _("Create")
        EDIT = "edit", _("Edit")
        DELETE = "delete", _("Delete")
        APPROVE = "approve", _("Approve")
        CUSTOM = "custom", _("Custom")

    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
        related_name="actions",
        verbose_name=_("feature"),
    )
    slug = models.CharField(_("slug"), max_length=250, unique=True)
    code = models.SlugField(_("code"), max_length=100)
    label = models.CharField(_("label"), max_length=150)
    category = models.CharField(
        _("category"),
        max_length=20,
        choices=Category.choices,
        default=Category.CUSTOM,
    )
    # Optional Django permission codename, same role as Feature.required_permission
    # but at the finer action granularity. sync_catalog never overwrites it.
    required_permission = models.CharField(
        _("required permission"), max_length=255, blank=True
    )
    is_active = models.BooleanField(_("is active"), default=True)
    order = models.IntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("action")
        verbose_name_plural = _("actions")
        ordering = ["feature__slug", "order", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["feature", "code"],
                name="access_action_unique_per_feature",
            ),
        ]

    def __str__(self) -> str:
        return self.slug


class OrgUnit(BaseModel):
    """A node in the organisation tree (company → division → team).

    Models the reporting structure: a supervisor unit owns several staff
    units, a manager unit owns several supervisor units, and so on. The level
    a user sits at is its position in this tree, so it stays dynamic and needs
    no hardcoded role table.
    """

    name = models.CharField(_("name"), max_length=150)
    slug = models.SlugField(_("slug"), max_length=150, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("parent"),
    )
    is_active = models.BooleanField(_("is active"), default=True)
    order = models.IntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("org unit")
        verbose_name_plural = _("org units")
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name


class OrgUnitMembership(BaseModel):
    """A user's membership in one org unit.

    ``user_id`` stays a plain UUID (R4): ``accounts.User`` lives in another
    module, so there is no ForeignKey - membership stores the id and callers
    resolve it through ``accounts.selectors``.
    """

    org_unit = models.ForeignKey(
        OrgUnit,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("org unit"),
    )
    user_id = models.UUIDField(_("user id"), db_index=True)

    class Meta:
        verbose_name = _("org unit membership")
        verbose_name_plural = _("org unit memberships")
        ordering = ["org_unit__slug"]
        constraints = [
            models.UniqueConstraint(
                fields=["org_unit", "user_id"],
                name="access_membership_unique_per_unit_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.org_unit}: {self.user_id}"


class FeatureGrant(BaseModel):
    """One access decision: who may (or may not) use a feature or action.

    A grant targets a whole feature, or one action inside it, and a grantee -
    a group, a user, or an org unit. Precedence is decided in one place:
    ``selectors.user_can`` for actions and ``selectors.user_can_access`` for
    menu visibility, both fail-closed by default.
    """

    class GranteeType(models.TextChoices):
        GROUP = "group", _("Group")
        USER = "user", _("User")
        ORG_UNIT = "org_unit", _("Org unit")

    class Effect(models.TextChoices):
        ALLOW = "allow", _("Allow")
        DENY = "deny", _("Deny")

    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
        related_name="grants",
        verbose_name=_("feature"),
    )
    # Null means "the whole feature"; set it to narrow the grant to one action.
    action = models.ForeignKey(
        Action,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="grants",
        verbose_name=_("action"),
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
    # OrgUnit lives in this same module, so a real FK is safe (R4 only forbids
    # cross-module FKs) and keeps referential integrity.
    org_unit = models.ForeignKey(
        OrgUnit,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="feature_grants",
        verbose_name=_("org unit"),
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
                        org_unit__isnull=True,
                    )
                    | models.Q(
                        grantee_type="user",
                        user_id__isnull=False,
                        group__isnull=True,
                        org_unit__isnull=True,
                    )
                    | models.Q(
                        grantee_type="org_unit",
                        org_unit__isnull=False,
                        group__isnull=True,
                        user_id__isnull=True,
                    )
                ),
                name="access_grant_exactly_one_grantee",
            ),
            # One decision per (feature or action) + grantee: re-granting goes
            # through services.grant_feature, which upserts instead of
            # duplicating. PostgreSQL treats NULLs as distinct, so the
            # feature-scoped and action-scoped constraints are split on
            # action__isnull to keep each one enforceable.
            models.UniqueConstraint(
                fields=["feature", "group"],
                condition=models.Q(grantee_type="group", action__isnull=True),
                name="access_grant_unique_group_feature",
            ),
            models.UniqueConstraint(
                fields=["feature", "action", "group"],
                condition=models.Q(grantee_type="group", action__isnull=False),
                name="access_grant_unique_group_action",
            ),
            models.UniqueConstraint(
                fields=["feature", "user_id"],
                condition=models.Q(grantee_type="user", action__isnull=True),
                name="access_grant_unique_user_feature",
            ),
            models.UniqueConstraint(
                fields=["feature", "action", "user_id"],
                condition=models.Q(grantee_type="user", action__isnull=False),
                name="access_grant_unique_user_action",
            ),
            models.UniqueConstraint(
                fields=["feature", "org_unit"],
                condition=models.Q(grantee_type="org_unit", action__isnull=True),
                name="access_grant_unique_orgunit_feature",
            ),
            models.UniqueConstraint(
                fields=["feature", "action", "org_unit"],
                condition=models.Q(grantee_type="org_unit", action__isnull=False),
                name="access_grant_unique_orgunit_action",
            ),
        ]

    def __str__(self) -> str:
        scope = self.feature.slug if self.action is None else self.action.slug
        if self.grantee_type == self.GranteeType.GROUP:
            return f"{scope}: {self.group}"
        if self.grantee_type == self.GranteeType.ORG_UNIT:
            return f"{scope}: {self.org_unit}"
        return f"{scope}: user {self.user_id}"
