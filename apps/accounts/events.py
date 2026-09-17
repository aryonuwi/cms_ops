"""Facts this module publishes. Other modules subscribe by name only."""

from apps.common.events import DomainEvent

USER_REGISTERED = "accounts.user_registered"
USER_DEACTIVATED = "accounts.user_deactivated"
USER_UPDATED = "accounts.user_updated"
USER_ACTIVATED = "accounts.user_activated"
USER_SUSPENDED = "accounts.user_suspended"
GROUP_ASSIGNED = "accounts.group_assigned"
GROUP_UNASSIGNED = "accounts.group_unassigned"
PERMISSION_GRANTED = "accounts.permission_granted"
PERMISSION_REVOKED = "accounts.permission_revoked"
USER_DELETED = "accounts.user_deleted"
TWO_FACTOR_SETUP_INITIATED = "accounts.two_factor_setup_initiated"
TWO_FACTOR_ENABLED = "accounts.two_factor_enabled"
TWO_FACTOR_DISABLED = "accounts.two_factor_disabled"
TWO_FACTOR_TAMPERED_RESET = "accounts.two_factor_tampered_reset"


def user_registered(*, user_id: str, email: str) -> DomainEvent:
    return DomainEvent(
        name=USER_REGISTERED, payload={"user_id": str(user_id), "email": email}
    )


def user_deactivated(*, user_id: str) -> DomainEvent:
    return DomainEvent(name=USER_DEACTIVATED, payload={"user_id": str(user_id)})


def user_updated(*, user_id: str) -> DomainEvent:
    return DomainEvent(name=USER_UPDATED, payload={"user_id": str(user_id)})


def user_activated(*, user_id: str) -> DomainEvent:
    return DomainEvent(name=USER_ACTIVATED, payload={"user_id": str(user_id)})


def user_suspended(*, user_id: str) -> DomainEvent:
    return DomainEvent(name=USER_SUSPENDED, payload={"user_id": str(user_id)})


def group_assigned(*, user_id: str, group_id: str) -> DomainEvent:
    return DomainEvent(
        name=GROUP_ASSIGNED,
        payload={"user_id": str(user_id), "group_id": str(group_id)},
    )


def group_unassigned(*, user_id: str, group_id: str) -> DomainEvent:
    return DomainEvent(
        name=GROUP_UNASSIGNED,
        payload={"user_id": str(user_id), "group_id": str(group_id)},
    )


def permission_granted(*, user_id: str, permission_codename: str) -> DomainEvent:
    return DomainEvent(
        name=PERMISSION_GRANTED,
        payload={
            "user_id": str(user_id),
            "permission_codename": permission_codename,
        },
    )


def permission_revoked(*, user_id: str, permission_codename: str) -> DomainEvent:
    return DomainEvent(
        name=PERMISSION_REVOKED,
        payload={
            "user_id": str(user_id),
            "permission_codename": permission_codename,
        },
    )


def user_deleted(*, user_id: str, email: str) -> DomainEvent:
    return DomainEvent(
        name=USER_DELETED,
        payload={"user_id": str(user_id), "email": email},
    )


def two_factor_setup_initiated(*, user_id: str) -> DomainEvent:
    return DomainEvent(
        name=TWO_FACTOR_SETUP_INITIATED,
        payload={"user_id": str(user_id)},
    )


def two_factor_enabled(*, user_id: str) -> DomainEvent:
    return DomainEvent(
        name=TWO_FACTOR_ENABLED,
        payload={"user_id": str(user_id)},
    )


def two_factor_disabled(*, user_id: str) -> DomainEvent:
    return DomainEvent(
        name=TWO_FACTOR_DISABLED,
        payload={"user_id": str(user_id)},
    )


def two_factor_tampered_reset(*, user_id: str) -> DomainEvent:
    return DomainEvent(
        name=TWO_FACTOR_TAMPERED_RESET,
        payload={"user_id": str(user_id)},
    )
