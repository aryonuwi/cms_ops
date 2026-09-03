"""A minimal in-process event bus.

Feature modules stay decoupled by publishing facts instead of calling each
other. Today `publish()` dispatches synchronously in the same process; when a
module moves onto its own service, only this file changes - swap the dispatch
for a broker (Kafka, RabbitMQ, SNS) and the publishers and subscribers stay
exactly as they are.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

Subscriber = Callable[["DomainEvent"], None]

_subscribers: dict[str, list[Subscriber]] = defaultdict(list)


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Something that already happened. Named in the past tense."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self) if is_dataclass(self) else dict(self.__dict__)
        data["occurred_at"] = self.occurred_at.isoformat()
        return data


def subscribe(event_name: str, handler: Subscriber) -> None:
    """Register `handler` for `event_name`. Call this from AppConfig.ready()."""
    if handler not in _subscribers[event_name]:
        _subscribers[event_name].append(handler)


def publish(event: DomainEvent) -> None:
    """Deliver `event` to its subscribers.

    A failing subscriber is logged and skipped: one module must not be able to
    break another, which is also how a real broker behaves.
    """
    logger.info("event.published", extra={"event": event.name, "id": event.event_id})

    for handler in _subscribers.get(event.name, []):
        try:
            handler(event)
        except Exception:  # noqa: BLE001 - isolation is the point
            logger.exception(
                "event.handler_failed",
                extra={"event": event.name, "handler": repr(handler)},
            )


def clear_subscribers() -> None:
    """Test helper - drops every registration."""
    _subscribers.clear()
