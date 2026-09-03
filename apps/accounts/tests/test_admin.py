from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

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
