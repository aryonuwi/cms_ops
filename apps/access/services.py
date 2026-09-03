"""Write-side API of the access module.

Every state change goes through here so validation, transactions and event
publication stay in one place - never in a view, admin or another module.
"""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.db import transaction

from apps.common.events import publish
from apps.common.navigation import iter_navigation_groups

from . import events
from .models import Feature, FeatureGrant


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
    effect: str = FeatureGrant.Effect.ALLOW,
) -> FeatureGrant:
    """Create - or update - the single grant for this feature + grantee.

    Re-submitting the same decision must not produce a duplicate row (the
    unique constraints forbid it anyway), so an upsert keeps the admin and
    future API callers forgiving.
    """
    if grantee_type == FeatureGrant.GranteeType.GROUP:
        if group is None:
            raise ValueError("A group grant requires a group.")
        grant, _created = FeatureGrant.objects.update_or_create(
            feature=feature,
            grantee_type=grantee_type,
            group=group,
            defaults={"effect": effect, "user_id": None},
        )
        grantee_id = str(group.pk)
    elif grantee_type == FeatureGrant.GranteeType.USER:
        if user_id is None:
            raise ValueError("A personal grant requires a user_id.")
        grant, _created = FeatureGrant.objects.update_or_create(
            feature=feature,
            grantee_type=grantee_type,
            user_id=user_id,
            defaults={"effect": effect, "group": None},
        )
        grantee_id = str(user_id)
    else:
        raise ValueError(f"Unknown grantee_type: {grantee_type!r}")

    transaction.on_commit(
        lambda: publish(
            events.feature_granted(
                feature_slug=feature.slug,
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
    grantee_id = (
        str(grant.group.pk) if grant.group is not None else str(grant.user_id)
    )
    feature_slug = grant.feature.slug
    grantee_type = grant.grantee_type
    effect = grant.effect

    grant.delete()

    transaction.on_commit(
        lambda: publish(
            events.feature_revoked(
                feature_slug=feature_slug,
                grantee_type=grantee_type,
                grantee_id=grantee_id,
                effect=effect,
            )
        )
    )


@transaction.atomic
def sync_features() -> tuple[int, int]:
    """Refresh the Feature catalog from navigation declarations.

    Code stays the source of truth for which features exist (ADR-007): this
    only records what modules declare so grants have stable rows to point at.
    Operator-managed columns (description, required_permission, is_active)
    are deliberately left untouched, and features that disappear from code
    are kept - deactivating them is an operator decision, not a sync side
    effect, because grants may still reference them.
    """
    created = updated = 0

    for app_name, group in iter_navigation_groups():
        for item in group.get("items", []):
            slug = item.get("feature")
            if not slug:
                continue
            _feature, was_created = Feature.objects.update_or_create(
                slug=slug,
                defaults={
                    "label": str(item.get("title", slug)),
                    "module": app_name,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

    transaction.on_commit(
        lambda: publish(events.features_synced(created=created, updated=updated))
    )
    return created, updated
