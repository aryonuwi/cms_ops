"""Actions this module exposes - scanned into the access catalog.

Feature slugs are the ones declared in ``navigation.py``. ``required_permission``
is the Django permission codename that enforcement checks on top of the grant.
"""

from django.utils.translation import gettext_lazy as _

ACTIONS = [
    {
        "feature": "accounts.users",
        "code": "view",
        "label": _("View user"),
        "category": "custom",
        "required_permission": "accounts.view_user",
    },
    {
        "feature": "accounts.users",
        "code": "create",
        "label": _("Create user"),
        "category": "create",
        "required_permission": "accounts.add_user",
    },
    {
        "feature": "accounts.users",
        "code": "edit",
        "label": _("Edit user"),
        "category": "edit",
        "required_permission": "accounts.change_user",
    },
    {
        "feature": "accounts.users",
        "code": "delete",
        "label": _("Delete user"),
        "category": "delete",
        "required_permission": "accounts.delete_user",
    },
]
