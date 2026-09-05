"""Facts this module publishes. Other modules subscribe by name only."""

from apps.common.events import DomainEvent

FEATURE_GRANTED = "access.feature_granted"
FEATURE_REVOKED = "access.feature_revoked"
CATALOG_SYNCED = "access.catalog_synced"


def feature_granted(
    *, feature_slug: str, grantee_type: str, grantee_id: str, effect: str
) -> DomainEvent:
    return DomainEvent(
        name=FEATURE_GRANTED,
        payload={
            "feature_slug": feature_slug,
            "grantee_type": grantee_type,
            "grantee_id": grantee_id,
            "effect": effect,
        },
    )


def feature_revoked(
    *, feature_slug: str, grantee_type: str, grantee_id: str, effect: str
) -> DomainEvent:
    return DomainEvent(
        name=FEATURE_REVOKED,
        payload={
            "feature_slug": feature_slug,
            "grantee_type": grantee_type,
            "grantee_id": grantee_id,
            "effect": effect,
        },
    )


def catalog_synced(
    *,
    modules_created: int,
    modules_updated: int,
    features_created: int,
    features_updated: int,
    actions_created: int,
    actions_updated: int,
) -> DomainEvent:
    return DomainEvent(
        name=CATALOG_SYNCED,
        payload={
            "modules_created": modules_created,
            "modules_updated": modules_updated,
            "features_created": features_created,
            "features_updated": features_updated,
            "actions_created": actions_created,
            "actions_updated": actions_updated,
        },
    )


ORG_UNIT_CREATED = "access.org_unit_created"
ORG_UNIT_MOVED = "access.org_unit_moved"
ORG_UNIT_MEMBER_ADDED = "access.org_unit_member_added"
ORG_UNIT_MEMBER_REMOVED = "access.org_unit_member_removed"


def org_unit_created(*, org_unit_slug: str, parent_slug: str | None) -> DomainEvent:
    return DomainEvent(
        name=ORG_UNIT_CREATED,
        payload={"org_unit_slug": org_unit_slug, "parent_slug": parent_slug},
    )


def org_unit_moved(*, org_unit_slug: str, parent_slug: str | None) -> DomainEvent:
    return DomainEvent(
        name=ORG_UNIT_MOVED,
        payload={"org_unit_slug": org_unit_slug, "parent_slug": parent_slug},
    )


def org_unit_member_added(*, org_unit_slug: str, user_id: str) -> DomainEvent:
    return DomainEvent(
        name=ORG_UNIT_MEMBER_ADDED,
        payload={"org_unit_slug": org_unit_slug, "user_id": user_id},
    )


def org_unit_member_removed(*, org_unit_slug: str, user_id: str) -> DomainEvent:
    return DomainEvent(
        name=ORG_UNIT_MEMBER_REMOVED,
        payload={"org_unit_slug": org_unit_slug, "user_id": user_id},
    )
