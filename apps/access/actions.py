"""Actions this module exposes - scanned into the access catalog.

The access module is superuser-only in practice, but its menus still appear in
the catalog so operators can see the full picture of what is installed.
"""

from django.utils.translation import gettext_lazy as _

ACTIONS = [
    {
        "feature": "access.features",
        "code": "manage",
        "label": _("Manage features"),
        "category": "custom",
    },
    {
        "feature": "access.feature_grants",
        "code": "manage",
        "label": _("Manage feature grants"),
        "category": "custom",
    },
    {
        "feature": "access.groups",
        "code": "manage",
        "label": _("Manage groups"),
        "category": "custom",
    },
]
