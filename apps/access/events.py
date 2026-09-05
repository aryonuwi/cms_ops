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
