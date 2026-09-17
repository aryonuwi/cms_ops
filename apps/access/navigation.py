"""This module's contribution to the Unfold sidebar."""

from django.http import HttpRequest
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _


def can_manage_access(request: HttpRequest) -> bool:
    # Handing out access is as sensitive as handing out staff rights, so it
    # stays superuser-only - mirroring the accounts module's stance.
    return request.user.is_active and request.user.is_superuser


NAVIGATION = [
    {
        "title": _("Access"),
        "separator": True,
        "collapsible": False,
        "order": 15,
        "items": [
            {
                "title": _("Modules"),
                "icon": "apps",
                "link": reverse_lazy("admin:access_module_changelist"),
                "permission": "apps.access.navigation.can_manage_access",
                "feature": "access.modules",
            },
            {
                "title": _("Features"),
                "icon": "widgets",
                "link": reverse_lazy("admin:access_feature_changelist"),
                "permission": "apps.access.navigation.can_manage_access",
                "feature": "access.features",
            },
            {
                "title": _("Actions"),
                "icon": "bolt",
                "link": reverse_lazy("admin:access_action_changelist"),
                "permission": "apps.access.navigation.can_manage_access",
                "feature": "access.actions",
            },
            {
                "title": _("Feature grants"),
                "icon": "key",
                "link": reverse_lazy("admin:access_featuregrant_changelist"),
                "permission": "apps.access.navigation.can_manage_access",
                "feature": "access.feature_grants",
            },
            {
                "title": _("Org units"),
                "icon": "account_tree",
                "link": reverse_lazy("admin:access_orgunit_changelist"),
                "permission": "apps.access.navigation.can_manage_access",
                "feature": "access.org_units",
            },
            {
                "title": _("Org unit memberships"),
                "icon": "group_add",
                "link": reverse_lazy("admin:access_orgunitmembership_changelist"),
                "permission": "apps.access.navigation.can_manage_access",
                "feature": "access.org_unit_memberships",
            },
            {
                "title": _("Groups"),
                "icon": "group",
                "link": reverse_lazy("admin:auth_group_changelist"),
                "permission": "apps.access.navigation.can_manage_access",
                "feature": "access.groups",
            },
        ],
    },
]
