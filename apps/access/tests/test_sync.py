"""The catalog sync: code declares, the database records, operators decide."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.access import services
from apps.access.models import Action, Feature, Module
from apps.common import events as bus


class SyncCatalogTests(TestCase):
    def tearDown(self):
        bus.clear_subscribers()

    def test_records_modules_features_and_actions(self):
        with self.captureOnCommitCallbacks(execute=True):
            result = services.sync_catalog()

        self.assertGreater(result.modules_created, 0)
        self.assertGreater(result.features_created, 0)
        self.assertGreater(result.actions_created, 0)

        module = Module.objects.get(slug="accounts")
        self.assertEqual(module.package, "apps.accounts")

        users = Feature.objects.get(slug="accounts.users")
        self.assertEqual(users.label, "Users")
        self.assertEqual(users.module, "accounts")

        action = Action.objects.get(slug="accounts.users.create")
        self.assertEqual(action.code, "create")
        self.assertEqual(action.feature_id, users.pk)
        self.assertEqual(action.category, "create")

    def test_is_idempotent(self):
        services.sync_catalog()
        with self.captureOnCommitCallbacks(execute=True):
            result = services.sync_catalog()

        self.assertEqual(result.modules_created, 0)
        self.assertEqual(result.features_created, 0)
        self.assertEqual(result.actions_created, 0)

    def test_never_touches_operator_managed_columns(self):
        services.sync_catalog()
        feature = Feature.objects.get(slug="accounts.users")
        feature.description = "operator note"
        feature.required_permission = "accounts.view_user"
        feature.is_active = False
        feature.save()

        action = Action.objects.get(slug="accounts.users.create")
        action.is_active = False
        action.save()

        services.sync_catalog()

        feature.refresh_from_db()
        self.assertEqual(feature.description, "operator note")
        self.assertEqual(feature.required_permission, "accounts.view_user")
        self.assertFalse(feature.is_active)

        action.refresh_from_db()
        self.assertFalse(action.is_active)

    def test_never_deletes_catalog_entries_missing_from_code(self):
        services.sync_catalog()
        Module.objects.create(slug="legacy", label="Legacy")
        feature = Feature.objects.create(
            slug="legacy.reports", label="Legacy reports", module="legacy"
        )
        Action.objects.create(
            feature=feature, slug="legacy.reports.view", code="view", label="View"
        )

        services.sync_catalog()

        self.assertTrue(Module.objects.filter(slug="legacy").exists())
        self.assertTrue(Feature.objects.filter(slug="legacy.reports").exists())
        self.assertTrue(Action.objects.filter(slug="legacy.reports.view").exists())

    def test_sync_catalog_command_reports_counts(self):
        out = StringIO()
        call_command("sync_catalog", stdout=out)
        self.assertIn("catalog:", out.getvalue())

    def test_sync_features_command_still_works(self):
        out = StringIO()
        call_command("sync_features", stdout=out)
        self.assertIn("features:", out.getvalue())

    def test_publishes_catalog_synced_after_commit(self):
        received = []
        bus.subscribe("access.catalog_synced", received.append)

        with self.captureOnCommitCallbacks(execute=True):
            result = services.sync_catalog()

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["modules_created"], result.modules_created)
        self.assertEqual(received[0].payload["features_created"], result.features_created)
        self.assertEqual(received[0].payload["actions_created"], result.actions_created)
