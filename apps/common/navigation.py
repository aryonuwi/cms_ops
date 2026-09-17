"""Assembles the Unfold sidebar from what each feature module declares.

A feature module exposes a module-level `NAVIGATION` list in its own
`navigation.py`:

    from django.urls import reverse_lazy

    NAVIGATION = [
        {
            "title": "Accounts",
            "separator": True,
            "order": 10,
            "items": [
                {
                    "title": "Users",
                    "icon": "person",
                    "link": reverse_lazy("admin:accounts_user_changelist"),
                    "permission": "apps.accounts.navigation.can_manage_users",
                    "feature": "accounts.users",  # optional, see below
                },
            ],
        }
    ]

The optional `feature` key names the item in the access module's catalog
(`sync_features` records it so grants can point at it); it is stripped before
the group reaches Unfold, which knows nothing about it.

Adding a module therefore never means editing a central list, and removing one
takes its menu entries with it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from importlib import import_module
from typing import Any

from django.apps import apps
from django.http import HttpRequest

logger = logging.getLogger(__name__)

DEFAULT_ORDER = 100


def iter_navigation_groups() -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(app_name, group)`` for every declared sidebar group.

    Shared by the sidebar builder and the access catalog sync so the two can
    never disagree about what was declared. A module whose navigation cannot
    be imported is logged and skipped - same containment as the sidebar
    itself.
    """
    for app_config in apps.get_app_configs():
        if not app_config.name.startswith("apps."):
            continue

        try:
            module = import_module(f"{app_config.name}.navigation")
        except ModuleNotFoundError:
            continue
        except Exception:  # noqa: BLE001
            logger.exception("navigation.import_failed", extra={"app": app_config.name})
            continue

        for group in getattr(module, "NAVIGATION", []):
            yield app_config.name, group


def iter_modules() -> Iterator[tuple[str, str, str]]:
    """Yield ``(slug, package, label)`` for every installed ``apps.*`` module.

    ``slug`` is the short app label (``AppConfig.label``), ``package`` the
    dotted import path and ``label`` the human-readable verbose name. Used by
    the access catalog sync so a module is recorded the moment it is installed.
    """
    for app_config in apps.get_app_configs():
        if not app_config.name.startswith("apps."):
            continue
        yield app_config.label, app_config.name, app_config.verbose_name


def iter_actions() -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(app_label, action)`` for every action a module declares.

    Mirrors ``iter_navigation_groups``: a module exposes an ``ACTIONS`` list in
    its own ``actions.py`` (referencing feature slugs declared in its
    ``navigation.py``). A module whose actions cannot be imported is logged and
    skipped, so one broken declaration cannot fail the whole catalog sync.
    """
    for app_config in apps.get_app_configs():
        if not app_config.name.startswith("apps."):
            continue
        try:
            module = import_module(f"{app_config.name}.actions")
        except ModuleNotFoundError:
            continue
        except Exception:  # noqa: BLE001
            logger.exception("actions.import_failed", extra={"app": app_config.name})
            continue
        for action in getattr(module, "ACTIONS", []):
            yield app_config.label, action


def build_sidebar_navigation(request: HttpRequest | None = None) -> list[dict[str, Any]]:
    """Collect and order every module's navigation groups.

    Called by Unfold on each admin request, so it must never raise: a broken
    module drops out of the menu instead of taking the admin down with it.
    """
    groups: list[dict[str, Any]] = []

    for _app_name, group in iter_navigation_groups():
        # `feature` is a declaration for the access catalog, not something the
        # sidebar template needs.
        items = [
            {key: value for key, value in item.items() if key != "feature"}
            for item in group.get("items", [])
        ]
        groups.append({**group, "items": items, "order": group.get("order", DEFAULT_ORDER)})

    groups.sort(key=lambda group: (group["order"], str(group.get("title", ""))))

    for group in groups:
        group.pop("order", None)

    return groups
