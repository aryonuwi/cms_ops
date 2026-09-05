from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase

from apps.access import services as access_services
from apps.access.models import Action, Feature
from apps.accounts.admin import UserAdmin

User = get_user_model()

PRIVILEGED_FIELDS = ["is_staff", "is_superuser", "groups", "user_permissions", "status"]


class UserAdminReadonlyTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = UserAdmin(User, admin_site=None)
        self.superuser = User.objects.create_superuser(
            email="root@example.com", password="pw"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com", password="pw", is_staff=True
        )

    def _readonly(self, user):
        request = self.factory.get("/admin/accounts/user/")
        request.user = user
        return self.admin.get_readonly_fields(request)

    def test_superuser_can_edit_privileged_fields(self):
        readonly = self._readonly(self.superuser)
        for field in PRIVILEGED_FIELDS:
            self.assertNotIn(field, readonly)

    def test_non_superuser_cannot_edit_privileged_fields(self):
        readonly = self._readonly(self.staff)
        for field in PRIVILEGED_FIELDS:
            self.assertIn(field, readonly)


class UserAdminEnforcementTests(TestCase):
    """A grant must block the URL (ADR-016), not just hide the menu."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="root@example.com", password="pw"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com", password="pw", is_staff=True
        )
        self.staff_no_grant = User.objects.create_user(
            email="nogrant@example.com", password="pw", is_staff=True
        )

        access_services.sync_catalog()
        feature = Feature.objects.get(slug="accounts.users")
        view_action = Action.objects.get(slug="accounts.users.view")

        view_user = Permission.objects.get(codename="view_user")
        self.staff.user_permissions.add(view_user)
        ops = Group.objects.create(name="ops")
        self.staff.groups.add(ops)
        access_services.grant_feature(
            feature=feature,
            grantee_type="group",
            group=ops,
            action=view_action,
        )

    def test_staff_without_grant_is_blocked(self):
        self.client.force_login(self.staff_no_grant)
        response = self.client.get("/admin/accounts/user/")
        self.assertEqual(response.status_code, 403)

    def test_staff_with_grant_and_permission_is_allowed(self):
        self.client.force_login(self.staff)
        response = self.client.get("/admin/accounts/user/")
        self.assertEqual(response.status_code, 200)

    def test_view_grant_cannot_save_changes(self):
        target = User.objects.create_user(email="target@example.com", password="pw")
        self.client.force_login(self.staff)
        url = f"/admin/accounts/user/{target.pk}/change/"

        # Viewing the form read-only is allowed through the view action...
        self.assertEqual(self.client.get(url).status_code, 200)

        # ...but saving an edit requires the edit action.
        response = self.client.post(
            url, {"email": "target@example.com", "first_name": "Changed"}
        )
        self.assertEqual(response.status_code, 403)
