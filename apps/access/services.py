"""Write-side API of the access module.

Every state change goes through here so validation, transactions and event
publication stay in one place - never in a view, admin or another module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from django.contrib.auth.models import Group
from django.db import transaction

from apps.common.events import publish
from apps.common.navigation import iter_actions, iter_modules, iter_navigation_groups

from . import events
from .models import Action, Feature, FeatureGrant, Module, OrgUnit, OrgUnitMembership


@transaction.atomic
def create_feature(
    *,
    slug: str,
    label: str,
    module: str = "",
    description: str = "",
    required_permission: str = "",
) -> Feature:
    """Register a feature that is not (or not yet) declared in code.

    Declarable features belong in a module's ``navigation.py``; this path is
    for operator-only capabilities that still deserve grant-based access.
    """
    feature = Feature.objects.create(
        slug=slug,
        label=label,
        module=module,
        description=description,
        required_permission=required_permission,
    )
    return feature


@transaction.atomic
def grant_feature(
    *,
    feature: Feature,
    grantee_type: str,
    group: Group | None = None,
    user_id: str | None = None,
    org_unit: OrgUnit | None = None,
    action: Action | None = None,
    effect: str = FeatureGrant.Effect.ALLOW,
) -> FeatureGrant:
    """Create - or update - the single grant for this feature (or action) + grantee.

    Re-submitting the same decision must not produce a duplicate row (the
    unique constraints forbid it anyway), so an upsert keeps the admin and
    future API callers forgiving. ``action=None`` grants the whole feature;
    setting it narrows the decision to that one action.
    """
    if action is not None and action.feature_id != feature.pk:
        raise ValueError("The action must belong to the granted feature.")

    if grantee_type == FeatureGrant.GranteeType.GROUP:
        if group is None:
            raise ValueError("A group grant requires a group.")
        grant, _created = FeatureGrant.objects.update_or_create(
            feature=feature,
            action=action,
            grantee_type=grantee_type,
            group=group,
            defaults={"effect": effect, "user_id": None, "org_unit": None},
        )
        grantee_id = str(group.pk)
    elif grantee_type == FeatureGrant.GranteeType.USER:
        if user_id is None:
            raise ValueError("A personal grant requires a user_id.")
        grant, _created = FeatureGrant.objects.update_or_create(
            feature=feature,
            action=action,
            grantee_type=grantee_type,
            user_id=user_id,
            defaults={"effect": effect, "group": None, "org_unit": None},
        )
        grantee_id = str(user_id)
    elif grantee_type == FeatureGrant.GranteeType.ORG_UNIT:
        if org_unit is None:
            raise ValueError("An org-unit grant requires an org_unit.")
        grant, _created = FeatureGrant.objects.update_or_create(
            feature=feature,
            action=action,
            grantee_type=grantee_type,
            org_unit=org_unit,
            defaults={"effect": effect, "group": None, "user_id": None},
        )
        grantee_id = str(org_unit.pk)
    else:
        raise ValueError(f"Unknown grantee_type: {grantee_type!r}")

    transaction.on_commit(
        lambda: publish(
            _granted_event(
                feature=feature,
                action=action,
                grantee_type=grantee_type,
                grantee_id=grantee_id,
                effect=effect,
            )
        )
    )
    return grant


@transaction.atomic
def revoke_feature(*, grant: FeatureGrant) -> None:
    """Remove one access decision and announce the previous state."""
    if grant.grantee_type == FeatureGrant.GranteeType.GROUP:
        grantee_id = str(grant.group.pk)
    elif grant.grantee_type == FeatureGrant.GranteeType.ORG_UNIT:
        grantee_id = str(grant.org_unit.pk)
    else:
        grantee_id = str(grant.user_id)

    feature_slug = grant.feature.slug
    action_slug = grant.action.slug if grant.action is not None else None
    grantee_type = grant.grantee_type
    effect = grant.effect

    grant.delete()

    transaction.on_commit(
        lambda: publish(
            _revoked_event(
                feature_slug=feature_slug,
                action_slug=action_slug,
                grantee_type=grantee_type,
                grantee_id=grantee_id,
                effect=effect,
            )
        )
    )


@transaction.atomic
def grant_module(
    *,
    module_slug: str,
    grantee_type: str,
    group: Group | None = None,
    user_id: str | None = None,
    org_unit: OrgUnit | None = None,
    effect: str = FeatureGrant.Effect.ALLOW,
) -> int:
    """Grant a whole module by fanning out to each of its features.

    A module-level decision is a convenience, not a new grant type: it writes
    one feature-scoped grant per feature under the module, so ``user_can``
    never has to resolve modules separately.
    """
    features = list(Feature.objects.filter(module=module_slug))
    for feature in features:
        grant_feature(
            feature=feature,
            grantee_type=grantee_type,
            group=group,
            user_id=user_id,
            org_unit=org_unit,
            effect=effect,
        )
    return len(features)


def _granted_event(
    *,
    feature: Feature,
    action: Action | None,
    grantee_type: str,
    grantee_id: str,
    effect: str,
):
    if action is None:
        return events.feature_granted(
            feature_slug=feature.slug,
            grantee_type=grantee_type,
            grantee_id=grantee_id,
            effect=effect,
        )
    return events.action_granted(
        feature_slug=feature.slug,
        action_slug=action.slug,
        grantee_type=grantee_type,
        grantee_id=grantee_id,
        effect=effect,
    )


def _revoked_event(
    *,
    feature_slug: str,
    action_slug: str | None,
    grantee_type: str,
    grantee_id: str,
    effect: str,
):
    if action_slug is None:
        return events.feature_revoked(
            feature_slug=feature_slug,
            grantee_type=grantee_type,
            grantee_id=grantee_id,
            effect=effect,
        )
    return events.action_revoked(
        feature_slug=feature_slug,
        action_slug=action_slug,
        grantee_type=grantee_type,
        grantee_id=grantee_id,
        effect=effect,
    )


@dataclass(frozen=True)
class SyncResult:
    """What one ``sync_catalog`` run created or updated."""

    modules_created: int = 0
    modules_updated: int = 0
    features_created: int = 0
    features_updated: int = 0
    actions_created: int = 0
    actions_updated: int = 0


@transaction.atomic
def create_module(
    *,
    slug: str,
    label: str,
    package: str = "",
    description: str = "",
    order: int = 0,
) -> Module:
    """Register a module that is not (or not yet) installed in the codebase."""
    return Module.objects.create(
        slug=slug,
        label=label,
        package=package,
        description=description,
        order=order,
    )


@transaction.atomic
def create_action(
    *,
    feature: Feature,
    code: str,
    label: str,
    category: str = Action.Category.CUSTOM,
    required_permission: str = "",
    order: int = 0,
) -> Action:
    """Register an action by hand; declarable actions belong in ``actions.py``."""
    return Action.objects.create(
        feature=feature,
        slug=f"{feature.slug}.{code}",
        code=code,
        label=label,
        category=category,
        required_permission=required_permission,
        order=order,
    )


@transaction.atomic
def sync_catalog() -> SyncResult:
    """Refresh the Module → Feature → Action catalog from code declarations.

    Code stays the source of truth (ADR-007): modules come from the app
    registry, features from each module's ``navigation.py`` and actions from
    each module's ``actions.py``. Every level is an idempotent upsert and
    nothing is ever deleted - entries that disappear from code are kept,
    because deactivating them is an operator decision and grants may still
    reference them. Operator-managed columns (description, required_permission,
    is_active, order) are deliberately left untouched.
    """
    result = SyncResult()

    # Modules first, so Feature.module can point at their slug.
    for slug, package, label in iter_modules():
        _module, was_created = Module.objects.update_or_create(
            slug=slug,
            defaults={"label": label, "package": package},
        )
        if was_created:
            result = replace(result, modules_created=result.modules_created + 1)
        else:
            result = replace(result, modules_updated=result.modules_updated + 1)

    for app_name, group in iter_navigation_groups():
        for item in group.get("items", []):
            slug = item.get("feature")
            if not slug:
                continue
            # ``app_name`` is the dotted "apps.accounts"; the short label is the
            # Module slug, which is what Feature.module stores.
            module_slug = app_name.rsplit(".", 1)[-1]
            _feature, was_created = Feature.objects.update_or_create(
                slug=slug,
                defaults={
                    "label": str(item.get("title", slug)),
                    "module": module_slug,
                },
            )
            if was_created:
                result = replace(result, features_created=result.features_created + 1)
            else:
                result = replace(result, features_updated=result.features_updated + 1)

    for app_label, declaration in iter_actions():
        feature_slug = declaration.get("feature")
        code = declaration.get("code")
        if not feature_slug or not code:
            continue
        feature = Feature.objects.filter(slug=feature_slug).first()
        if feature is None:
            # An action declared for a feature absent from navigation.py: record
            # the feature too, so the action has a home and grants can point at it.
            feature = Feature.objects.create(
                slug=feature_slug,
                label=str(feature_slug),
                module=app_label,
            )
        action_slug = f"{feature_slug}.{code}"
        _action, was_created = Action.objects.update_or_create(
            slug=action_slug,
            defaults={
                "feature": feature,
                "code": code,
                "label": str(declaration.get("label", code)),
                "category": declaration.get("category", Action.Category.CUSTOM),
                "required_permission": declaration.get("required_permission", ""),
            },
        )
        if was_created:
            result = replace(result, actions_created=result.actions_created + 1)
        else:
            result = replace(result, actions_updated=result.actions_updated + 1)

    transaction.on_commit(lambda: publish(events.catalog_synced(**asdict(result))))
    return result


def _would_cycle(org_unit: OrgUnit, new_parent: OrgUnit) -> bool:
    """True if ``new_parent`` is ``org_unit`` or one of its descendants."""
    node = new_parent
    while node is not None:
        if node.pk == org_unit.pk:
            return True
        node = node.parent
    return False


@transaction.atomic
def create_org_unit(
    *, name: str, slug: str, parent: OrgUnit | None = None, order: int = 0
) -> OrgUnit:
    """Create a node in the organisation tree."""
    org_unit = OrgUnit.objects.create(name=name, slug=slug, parent=parent, order=order)
    transaction.on_commit(
        lambda: publish(
            events.org_unit_created(
                org_unit_slug=org_unit.slug,
                parent_slug=org_unit.parent.slug if org_unit.parent is not None else None,
            )
        )
    )
    return org_unit


@transaction.atomic
def move_org_unit(
    *, org_unit: OrgUnit, new_parent: OrgUnit | None = None
) -> OrgUnit:
    """Re-parent a node, refusing to create a cycle."""
    if new_parent is not None and _would_cycle(org_unit, new_parent):
        raise ValueError("Cannot move an org unit under its own descendant.")
    org_unit.parent = new_parent
    org_unit.save(update_fields=["parent", "updated_at"])
    transaction.on_commit(
        lambda: publish(
            events.org_unit_moved(
                org_unit_slug=org_unit.slug,
                parent_slug=new_parent.slug if new_parent is not None else None,
            )
        )
    )
    return org_unit


@transaction.atomic
def add_org_member(*, org_unit: OrgUnit, user_id: str) -> OrgUnitMembership:
    """Add a user to an org unit once, announcing only a real change."""
    membership, created = OrgUnitMembership.objects.get_or_create(
        org_unit=org_unit, user_id=user_id
    )
    if created:
        transaction.on_commit(
            lambda: publish(
                events.org_unit_member_added(
                    org_unit_slug=org_unit.slug, user_id=str(user_id)
                )
            )
        )
    return membership


@transaction.atomic
def remove_org_member(*, membership: OrgUnitMembership) -> None:
    """Remove one membership and announce the previous state."""
    org_unit_slug = membership.org_unit.slug
    user_id = str(membership.user_id)
    membership.delete()
    transaction.on_commit(
        lambda: publish(
            events.org_unit_member_removed(
                org_unit_slug=org_unit_slug, user_id=user_id
            )
        )
    )
