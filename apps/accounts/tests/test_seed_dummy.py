"""Akun dummy harus staff-tapi-bukan-superuser (supaya tunduk pada
FeatureGrant, bukan bypass seperti seed_admin), dan seeding-nya harus
seaman/seidempoten seed_admin.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.common import events as bus

User = get_user_model()

SEED = {
    "SEED_DUMMY_EMAIL": "dummy@ops.local",
    "SEED_DUMMY_PASSWORD": "OpsViews!Dummy2026",
    "DEBUG": True,
}


@override_settings(**SEED)
class SeedDummyTests(TestCase):
    def tearDown(self):
        bus.clear_subscribers()

    def _run(self, **options) -> str:
        out = StringIO()
        call_command("seed_dummy", stdout=out, **options)
        return out.getvalue()

    def test_creates_non_superuser_staff(self):
        output = self._run()

        user = User.objects.get(email="dummy@ops.local")
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("OpsViews!Dummy2026"))
        self.assertEqual(user.status, User.Status.ACTIVE)
        self.assertIn("dibuat", output)

    def test_publishes_user_registered(self):
        received = []
        bus.subscribe("accounts.user_registered", received.append)

        with self.captureOnCommitCallbacks(execute=True):
            self._run()

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["email"], "dummy@ops.local")

    def test_is_idempotent_and_keeps_existing_password(self):
        self._run()
        User.objects.filter(email="dummy@ops.local").update(first_name="Dipakai")

        output = self._run()

        self.assertEqual(User.objects.filter(email="dummy@ops.local").count(), 1)
        self.assertEqual(
            User.objects.get(email="dummy@ops.local").first_name, "Dipakai"
        )
        self.assertIn("dilewati", output)

    @override_settings(SEED_DUMMY_EMAIL="", SEED_DUMMY_PASSWORD="")
    def test_fails_loudly_when_unconfigured(self):
        with self.assertRaises(CommandError):
            self._run()
        self.assertFalse(User.objects.exists())

    @override_settings(DEBUG=False)
    def test_refuses_without_force_when_debug_off(self):
        with self.assertRaises(CommandError):
            self._run()
        self.assertFalse(User.objects.exists())

    @override_settings(DEBUG=False)
    def test_force_allows_deliberate_seeding_with_debug_off(self):
        self._run(force=True)

        self.assertTrue(User.objects.filter(email="dummy@ops.local").exists())
