"""The access admins stay superuser-only at the URL level."""

from django.test import TestCase

from apps.accounts import services as accounts_services

PASSWORD = "correct-horse-battery"

ACCESS_URLS = (
    "/admin/access/module/",
    "/admin/access/feature/",
    "/admin/access/action/",
    "/admin/access/featuregrant/",
    "/admin/access/orgunit/",
    "/admin/access/orgunitmembership/",
    "/admin/auth/group/",
)


class AccessAdminSelfGuardTests(TestCase):
    def setUp(self):
        self.superuser = accounts_services.register_user(
            email="root@example.com", password=PASSWORD
        )
        self.superuser.is_superuser = True
        self.superuser.is_staff = True
        self.superuser.save()

        self.staff = accounts_services.register_user(
            email="staff@example.com", password=PASSWORD, is_staff=True
        )

    def test_staff_cannot_open_access_changelists(self):
        self.client.force_login(self.staff)
        for url in ACCESS_URLS:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_superuser_can_open_access_changelists(self):
        self.client.force_login(self.superuser)
        for url in ACCESS_URLS:
            self.assertEqual(self.client.get(url).status_code, 200, url)
