"""The catalog sync: code declares, the database records, operators decide."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.access import services
from apps.access.models import Feature
from apps.common import events as bus


class SyncFeaturesTests(TestCase):
    def tearDown(self):
        bus.clear_subscribers()

    def test_records_every_declared_feature(self):
        with self.captureOnCommitCallbacks(execute=True):
            created, _updated = services.sync_features()

        self.assertGreater(created, 0)
        users = Feature.objects.get(slug="accounts.users")
        self.assertEqual(users.label, "Users")
        self.assertEqual(users.module, "apps.accounts")

    def test_is_idempotent(self):
        services.sync_features()
        with self.captureOnCommitCallbacks(execute=True):
            created, updated = services.sync_features()
        self.assertEqual(created, 0)
        self.assertGreater(updated, 0)

    def test_never_touches_operator_managed_columns(self):
        services.sync_features()
        feature = Feature.objects.get(slug="accounts.users")
        feature.description = "operator note"
        feature.required_permission = "accounts.view_user"
        feature.is_active = False
        feature.save()

        services.sync_features()

        feature.refresh_from_db()
        self.assertEqual(feature.description, "operator note")
        self.assertEqual(feature.required_permission, "accounts.view_user")
        self.assertFalse(feature.is_active)

    def test_management_command_reports_counts(self):
        out = StringIO()
        call_command("sync_features", stdout=out)
        self.assertIn("features:", out.getvalue())

    def test_publishes_sync_event_after_commit(self):
        received = []
        bus.subscribe("access.features_synced", received.append)

        with self.captureOnCommitCallbacks(execute=True):
            created, _updated = services.sync_features()

        self.assertEqual(len(received), 1)
        self.assertGreater(created, 0)
        self.assertEqual(received[0].payload["created"], created)
