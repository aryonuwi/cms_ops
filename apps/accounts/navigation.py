"""This module's contribution to the Unfold sidebar."""

from django.http import HttpRequest
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from apps.access import selectors as access_selectors


def can_manage_users(request: HttpRequest) -> bool:
    # Delegated to the access module so group and personal grants govern this
    # menu exactly like every other feature; superusers pass without grants.
    return access_selectors.user_can_access(request.user, "accounts.users")


NAVIGATION = [
    {
        "title": _("Accounts"),
        "separator": True,
        "collapsible": False,
        "order": 10,
        "items": [
            {
                "title": _("Users"),
                "icon": "person",
                "link": reverse_lazy("admin:accounts_user_changelist"),
                "permission": "apps.accounts.navigation.can_manage_users",
                "feature": "accounts.users",
            },
        ],
    },
]
