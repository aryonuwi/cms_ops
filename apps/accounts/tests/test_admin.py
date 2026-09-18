import pyotp
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.access import services as access_services
from apps.access.models import Action, Feature
from apps.accounts.admin import UserAdmin
from apps.accounts import services

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

    def test_non_superuser_cannot_change_or_delete_staff_objects(self):
        request = self.factory.get("/admin/accounts/user/")
        request.user = self.staff
        target = User.objects.create_user(
            email="target-staff@example.com",
            password="pw",
            is_staff=True,
        )

        self.assertFalse(self.admin.has_change_permission(request, target))
        self.assertFalse(self.admin.has_delete_permission(request, target))

    def test_change_form_uses_one_inline_password_form(self):
        credential_fields = UserAdmin.fieldsets[0][1]["fields"]

        self.assertNotIn("password", credential_fields)
        self.assertIn("new_password", credential_fields)
        self.assertIn("confirm_new_password", credential_fields)


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


@override_settings(
    TWO_FACTOR_ENCRYPTION_KEY="dGhpcy1pcy1hLXNhbXBsZS0zMi1ieXRlLWtleS0xMjM0NTY="
)
class UserAdminTwoFactorResetTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="root@example.com", password="pw"
        )
        self.target = User.objects.create_user(
            email="target@example.com", password="pw", is_staff=True
        )
        secret, _uri = services.setup_two_factor(user=self.target)
        services.enable_two_factor(
            user=self.target,
            code=pyotp.TOTP(secret).now(),
        )

    def test_superuser_can_reset_two_factor_from_user_detail(self):
        self.client.force_login(self.superuser)
        url = reverse(
            "admin:accounts_user_reset_two_factor",
            args=[self.target.pk],
        )
        change_page = self.client.get(
            reverse("admin:accounts_user_change", args=[self.target.pk])
        )
        self.assertEqual(change_page.status_code, 200)
        self.assertContains(change_page, url)
        self.assertContains(change_page, "activeFieldsetTab")
        self.assertNotContains(change_page, 'id="id_password"')

        confirmation = self.client.get(url)
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, self.target.email)

        response = self.client.post(url)

        self.assertRedirects(
            response,
            reverse("admin:accounts_user_change", args=[self.target.pk]),
        )
        self.assertFalse(services.selectors.is_two_factor_enabled(self.target))

    def test_builtin_per_user_password_route_is_not_a_third_reset_flow(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            f"/admin/accounts/user/{self.target.pk}/password/"
        )

        self.assertEqual(response.status_code, 302)
        route_names = {
            pattern.name for pattern in admin.site._registry[User].get_urls()
        }
        self.assertNotIn("auth_user_password_change", route_names)
