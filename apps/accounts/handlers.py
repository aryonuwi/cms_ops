"""Subscriptions to other modules' events.

Wired from `AccountsConfig.ready()`. Keeping them here means a module never
reaches into another module's internals - it only reacts to published facts.
"""

from apps.common import events as bus


def register_subscriptions() -> None:
    # Example:
    #   bus.subscribe("billing.subscription_cancelled", _on_subscription_cancelled)
    pass


register_subscriptions()

__all__ = ["register_subscriptions", "bus"]
