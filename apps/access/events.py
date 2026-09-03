"""Facts this module publishes. Other modules subscribe by name only."""

from apps.common.events import DomainEvent

FEATURE_GRANTED = "access.feature_granted"
FEATURE_REVOKED = "access.feature_revoked"
FEATURES_SYNCED = "access.features_synced"


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


def features_synced(*, created: int, updated: int) -> DomainEvent:
    return DomainEvent(
        name=FEATURES_SYNCED,
        payload={"created": created, "updated": updated},
    )
