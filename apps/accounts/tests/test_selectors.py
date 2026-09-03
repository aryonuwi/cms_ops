from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from apps.accounts import selectors

User = get_user_model()


class ListUserGroupsTests(TestCase):
    def test_ordered_by_name(self):
        user = User.objects.create_user(email="g@example.com", password="pw")
        for name in ("zeta", "alpha"):
            Group.objects.create(name=name)
        user.groups.add(
            Group.objects.get(name="zeta"), Group.objects.get(name="alpha")
        )

        names = [g.name for g in selectors.list_user_groups(user)]
        self.assertEqual(names, ["alpha", "zeta"])


class GetUserPermissionsTests(TestCase):
    def test_inactive_user_has_no_permissions(self):
        user = User.objects.create_user(
            email="inactive@example.com", password="pw", is_active=False
        )
        self.assertEqual(selectors.get_user_permissions(user), set())

    def test_superuser_has_accounts_permission(self):
        superuser = User.objects.create_superuser(
            email="root@example.com", password="pw"
        )
        self.assertIn("accounts.view_user", selectors.get_user_permissions(superuser))

    def test_group_and_personal_permissions_both_visible(self):
        user = User.objects.create_user(email="staff@example.com", password="pw")

        group = Group.objects.create(name="Viewers")
        user.groups.add(group)
        group_perm = Permission.objects.get(
            content_type__app_label="accounts", codename="view_user"
        )
        group.permissions.add(group_perm)

        personal_perm = Permission.objects.get(
            content_type__app_label="access", codename="view_feature"
        )
        user.user_permissions.add(personal_perm)

        perms = selectors.get_user_permissions(user)
        self.assertIn("accounts.view_user", perms)
        self.assertIn("access.view_feature", perms)
