"""Subscriptions to other modules' events.

Wired from `AccessConfig.ready()`. Keeping them here means a module never
reaches into another module's internals - it only reacts to published facts.
"""

from apps.common import events as bus


def register_subscriptions() -> None:
    # Deliberately nothing yet. In particular, accounts.user_deactivated does
    # NOT delete personal grants: user_can_access already fail-closes for
    # inactive users, and wiping grants would destroy operator configuration
    # on what may be a temporary deactivation.
    pass


register_subscriptions()

__all__ = ["register_subscriptions", "bus"]
