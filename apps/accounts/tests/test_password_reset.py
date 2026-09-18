from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts import selectors, services
from apps.accounts.models import UserActivity


@override_settings(
    MAILERS={
        "default": {
            "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
        }
    }
)
class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = services.register_user(
            email="reset@example.com",
            password="OldPassword!123",
        )

    def test_admin_service_emails_link_and_link_can_be_used_once(self):
        reset_url = services.send_password_reset_link(
            user=self.user,
            site_url="http://testserver/",
            requested_by_id=self.user.pk,
            ip_address="192.0.2.10",
            user_agent="test-agent",
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn(reset_url, mail.outbox[0].body)
        self.assertNotIn("OldPassword!123", mail.outbox[0].body)

        response = self.client.post(
            reset_url,
            {
                "new_password": "NewPassword!456",
                "confirm_new_password": "NewPassword!456",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassword!456"))
        self.assertEqual(
            selectors.list_user_activities(user_id=self.user.pk, limit=1).first().action,
            UserActivity.Action.PASSWORD_RESET_COMPLETED,
        )

        self.assertEqual(self.client.get(reset_url).status_code, 400)


class UserAdminPasswordResetTests(TestCase):
    def setUp(self):
        self.superuser = services.register_user(
            email="root@example.com",
            password="RootPassword!123",
            is_staff=True,
            is_superuser=True,
        )
        self.target = services.register_user(
            email="target@example.com",
            password="TargetPassword!123",
        )

    def test_non_superuser_cannot_send_reset_link(self):
        staff = services.register_user(
            email="staff@example.com",
            password="StaffPassword!123",
            is_staff=True,
        )
        self.client.force_login(staff)
        url = reverse(
            "admin:accounts_user_send_password_reset",
            args=[self.target.pk],
        )

        self.assertEqual(self.client.get(url).status_code, 403)

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            }
        }
    )
    def test_superuser_can_send_reset_link_from_user_detail(self):
        self.client.force_login(self.superuser)
        url = reverse(
            "admin:accounts_user_send_password_reset",
            args=[self.target.pk],
        )
        change_url = reverse("admin:accounts_user_change", args=[self.target.pk])
        list_url = reverse("admin:accounts_user_changelist")

        list_page = self.client.get(list_url)
        self.assertContains(list_page, url)
        self.assertContains(list_page, "Kirim Link")

        change_page = self.client.get(change_url)
        self.assertContains(change_page, url)
        self.assertContains(change_page, "Generate &amp; Kirim Link Reset Password")
        self.assertContains(change_page, "data-password-policy")
        self.assertContains(change_page, "Minimal 8 karakter")
        self.assertContains(change_page, "Aktivitas User")

        confirmation = self.client.get(url)
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, self.target.email)

        response = self.client.post(url)

        self.assertRedirects(response, change_url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("password-reset", mail.outbox[0].body)
        self.assertEqual(
            selectors.list_user_activities(user_id=self.target.pk, limit=1).first().action,
            UserActivity.Action.PASSWORD_RESET_REQUESTED,
        )


class UserActivitySignalTests(TestCase):
    def setUp(self):
        self.user = services.register_user(
            email="activity@example.com",
            password="ActivityPassword!123",
        )

    def test_login_and_failed_login_are_recorded(self):
        self.assertTrue(
            self.client.login(
                email=self.user.email,
                password="ActivityPassword!123",
            )
        )
        self.assertFalse(
            self.client.login(
                email=self.user.email,
                password="wrong-password",
            )
        )

        actions = set(
            selectors.list_user_activities(user_id=self.user.pk, limit=10).values_list(
                "action", flat=True
            )
        )
        self.assertIn(UserActivity.Action.LOGIN_SUCCESS, actions)
        self.assertIn(UserActivity.Action.LOGIN_FAILED, actions)
