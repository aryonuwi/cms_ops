"""Read-side API of the access module.

The one function other modules care about is ``user_can_access`` - the single
point where menu visibility is decided, so every sidebar entry that opts in
evaluates by the same rules.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models import Q, QuerySet

from .models import Action, Feature, FeatureGrant, Module, OrgUnit, OrgUnitMembership


def get_feature_by_slug(slug: str) -> Feature | None:
    return Feature.objects.filter(slug=slug).first()


def list_features(*, include_inactive: bool = False) -> QuerySet[Feature]:
    """The feature catalog, active entries only unless told otherwise."""
    queryset = Feature.objects.all()
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset


def get_module_by_slug(slug: str) -> Module | None:
    return Module.objects.filter(slug=slug).first()


def list_modules(*, include_inactive: bool = False) -> QuerySet[Module]:
    """The module catalog, active entries only unless told otherwise."""
    queryset = Module.objects.all()
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset


def list_actions(
    *, feature_slug: str | None = None, include_inactive: bool = False
) -> QuerySet[Action]:
    """Actions, optionally narrowed to one feature."""
    queryset = Action.objects.select_related("feature")
    if not include_inactive:
        queryset = queryset.filter(is_active=True, feature__is_active=True)
    if feature_slug is not None:
        queryset = queryset.filter(feature__slug=feature_slug)
    return queryset


def get_action_by_slug(slug: str) -> Action | None:
    return Action.objects.filter(slug=slug).first()


def list_grants(
    *, feature_slug: str | None = None, grantee_type: str | None = None
) -> QuerySet[FeatureGrant]:
    """Grants, optionally narrowed to one feature or grantee type."""
    queryset = FeatureGrant.objects.select_related("feature", "group")
    if feature_slug is not None:
        queryset = queryset.filter(feature__slug=feature_slug)
    if grantee_type is not None:
        queryset = queryset.filter(grantee_type=grantee_type)
    return queryset


def user_feature_grants(user: AbstractBaseUser) -> QuerySet[FeatureGrant]:
    """Every grant that touches ``user`` - via any group or a personal grant.

    Used by the accounts admin to show effective access without importing the
    user model; grantee types stay symbolic (no raw strings) so a rename can
    never silently break the filter.
    """
    group_ids = list(user.groups.values_list("pk", flat=True))
    return FeatureGrant.objects.select_related("feature", "group").filter(
        Q(grantee_type=FeatureGrant.GranteeType.GROUP, group_id__in=group_ids)
        | Q(grantee_type=FeatureGrant.GranteeType.USER, user_id=user.pk)
    )


def user_can_access(
    user: AbstractBaseUser | AnonymousUser, feature_slug: str
) -> bool:
    """Decide whether ``user`` may see and use the feature ``feature_slug``.

    Precedence, fail-closed at every step:

    * inactive or anonymous user -> ``False``
    * superuser -> ``True`` (bypasses grants, but not ``required_permission``:
      superusers hold every permission anyway)
    * unknown or deactivated feature -> ``False``
    * personal deny -> ``False``; personal allow -> ``True`` (most specific
      decision wins, so a personal allow survives a group deny)
    * group deny -> ``False``; group allow -> ``True``
    * otherwise -> ``False`` (default deny)
    """
    if not getattr(user, "is_active", False):
        return False
    if user.is_superuser:
        return True

    feature = Feature.objects.filter(slug=feature_slug, is_active=True).first()
    if feature is None:
        return False

    # Visibility and enforcement must agree: a menu that maps to a Django
    # permission stays hidden until the user actually holds that permission.
    if feature.required_permission and not user.has_perm(
        feature.required_permission
    ):
        return False

    group_ids = list(user.groups.values_list("pk", flat=True))
    grantee_types_and_effects = (
        FeatureGrant.objects.filter(feature=feature)
        .filter(
            Q(grantee_type=FeatureGrant.GranteeType.USER, user_id=user.pk)
            | Q(grantee_type=FeatureGrant.GranteeType.GROUP, group_id__in=group_ids)
        )
        .values_list("grantee_type", "effect")
    )

    personal_allow = personal_deny = group_allow = group_deny = False
    for grantee_type, effect in grantee_types_and_effects:
        if grantee_type == FeatureGrant.GranteeType.USER:
            if effect == FeatureGrant.Effect.DENY:
                personal_deny = True
            else:
                personal_allow = True
        else:
            if effect == FeatureGrant.Effect.DENY:
                group_deny = True
            else:
                group_allow = True

    if personal_deny:
        return False
    if personal_allow:
        return True
    if group_deny:
        return False
    return group_allow


def effective_features(user: AbstractBaseUser | AnonymousUser) -> set[str]:
    """Slugs of every active feature ``user`` can reach.

    Built on top of ``user_can_access`` so bulk checks can never drift from
    the per-feature decision.
    """
    return {
        slug
        for slug in list_features().values_list("slug", flat=True)
        if user_can_access(user, slug)
    }


def user_can(user: AbstractBaseUser | AnonymousUser, action_slug: str) -> bool:
    """Decide whether ``user`` may perform the action ``action_slug``.

    Single point of evaluation for action-level access, fail-closed at every
    step. Precedence:

    * inactive or anonymous user -> ``False``
    * superuser -> ``True``
    * unknown, inactive feature or action -> ``False``
    * ``required_permission`` (action, then feature) not held -> ``False``
    * action-scoped grant beats feature-scoped grant
    * within one scope: personal > org unit (incl. ancestors) > group, and
      deny > allow at the same grantee level
    * otherwise -> ``False``
    """
    if not getattr(user, "is_active", False):
        return False
    if user.is_superuser:
        return True

    action = (
        Action.objects.select_related("feature")
        .filter(slug=action_slug, is_active=True, feature__is_active=True)
        .first()
    )
    if action is None:
        return False

    feature = action.feature
    if action.required_permission and not user.has_perm(action.required_permission):
        return False
    if feature.required_permission and not user.has_perm(feature.required_permission):
        return False

    group_ids = list(user.groups.values_list("pk", flat=True))
    org_unit_ids = effective_org_unit_ids(user)

    rows = list(
        FeatureGrant.objects.filter(feature=feature)
        .filter(Q(action=action) | Q(action__isnull=True))
        .filter(
            Q(grantee_type=FeatureGrant.GranteeType.USER, user_id=user.pk)
            | Q(grantee_type=FeatureGrant.GranteeType.GROUP, group_id__in=group_ids)
            | Q(
                grantee_type=FeatureGrant.GranteeType.ORG_UNIT,
                org_unit_id__in=org_unit_ids,
            )
        )
        .values_list("action_id", "grantee_type", "effect")
    )

    action_rows = [row for row in rows if row[0] == action.pk]
    feature_rows = [row for row in rows if row[0] is None]

    decision = _scope_decision(action_rows)
    if decision is None:
        decision = _scope_decision(feature_rows)
    return bool(decision) if decision is not None else False


def _scope_decision(rows) -> bool | None:
    """Resolve one grant scope to allow / deny / undecided.

    ``rows`` are ``(action_id, grantee_type, effect)`` triples already narrowed
    to a single scope. Grantee specificity: personal > org unit > group; deny
    outranks allow within one grantee type.
    """
    for grantee_type in (
        FeatureGrant.GranteeType.USER,
        FeatureGrant.GranteeType.ORG_UNIT,
        FeatureGrant.GranteeType.GROUP,
    ):
        allow = deny = False
        for _action_id, row_grantee_type, effect in rows:
            if row_grantee_type != grantee_type:
                continue
            if effect == FeatureGrant.Effect.DENY:
                deny = True
            else:
                allow = True
        if deny:
            return False
        if allow:
            return True
    return None


def list_org_units(*, include_inactive: bool = False) -> QuerySet[OrgUnit]:
    """The organisation tree's nodes, active ones only unless told otherwise."""
    queryset = OrgUnit.objects.all()
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset


def effective_org_unit_ids(user: AbstractBaseUser | AnonymousUser) -> set[str]:
    """Ids of every org unit ``user`` belongs to, plus all ancestors.

    A grant on a manager unit must reach the staff units below it, so ancestry
    is resolved here once per evaluation instead of per grant.
    """
    if not getattr(user, "is_active", False):
        return set()
    member_ids = set(
        OrgUnitMembership.objects.filter(user_id=user.pk).values_list(
            "org_unit_id", flat=True
        )
    )
    if not member_ids:
        return set()
    # Walk parents in memory: org tables are small, so one lookup beats N+1
    # queries down a deep chain.
    parents = dict(
        OrgUnit.objects.exclude(parent__isnull=True).values_list("id", "parent_id")
    )
    result = set(member_ids)
    for unit_id in member_ids:
        current = unit_id
        seen = set()
        while current in parents and current not in seen:
            seen.add(current)
            current = parents[current]
            result.add(current)
    return result


def list_org_unit_member_ids(org_unit: OrgUnit) -> set[str]:
    """Raw user ids in ``org_unit`` - resolve them via ``accounts.selectors``."""
    return set(
        OrgUnitMembership.objects.filter(org_unit=org_unit).values_list(
            "user_id", flat=True
        )
    )
