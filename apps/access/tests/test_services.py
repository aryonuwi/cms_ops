"""Service-layer behaviour: upsert semantics, events and database guards."""

from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.access import services
from apps.access.models import Feature, FeatureGrant
from apps.common import events as bus


class GrantFeatureTests(TestCase):
    def tearDown(self):
        bus.clear_subscribers()

    def setUp(self):
        self.feature = Feature.objects.create(slug="reports.overview", label="Overview")
        self.ops = Group.objects.create(name="ops")

    def test_creates_group_grant_and_publishes_after_commit(self):
        received = []
        bus.subscribe("access.feature_granted", received.append)

        with self.captureOnCommitCallbacks(execute=True):
            grant = services.grant_feature(
                feature=self.feature,
                grantee_type="group",
                group=self.ops,
            )

        self.assertEqual(grant.effect, "allow")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["feature_slug"], "reports.overview")
        self.assertEqual(received[0].payload["grantee_type"], "group")

    def test_regrant_upserts_instead_of_duplicating(self):
        services.grant_feature(
            feature=self.feature, grantee_type="group", group=self.ops, effect="allow"
        )
        services.grant_feature(
            feature=self.feature, grantee_type="group", group=self.ops, effect="deny"
        )

        grants = FeatureGrant.objects.filter(feature=self.feature)
        self.assertEqual(grants.count(), 1)
        self.assertEqual(grants.get().effect, "deny")

    def test_rejects_grant_without_matching_grantee(self):
        with self.assertRaises(ValueError):
            services.grant_feature(feature=self.feature, grantee_type="group")
        with self.assertRaises(ValueError):
            services.grant_feature(feature=self.feature, grantee_type="user")
        with self.assertRaises(ValueError):
            services.grant_feature(
                feature=self.feature, grantee_type="team", group=self.ops
            )

    def test_database_rejects_a_grant_with_no_grantee(self):
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                FeatureGrant.objects.create(
                    feature=self.feature, grantee_type="group"
                )

    def test_database_rejects_duplicate_group_grant(self):
        services.grant_feature(
            feature=self.feature, grantee_type="group", group=self.ops
        )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                FeatureGrant.objects.create(
                    feature=self.feature, grantee_type="group", group=self.ops
                )

    def test_revoke_feature_publishes_previous_state(self):
        grant = services.grant_feature(
            feature=self.feature, grantee_type="group", group=self.ops
        )
        received = []
        bus.subscribe("access.feature_revoked", received.append)

        with self.captureOnCommitCallbacks(execute=True):
            services.revoke_feature(grant=grant)

        self.assertFalse(FeatureGrant.objects.filter(pk=grant.pk).exists())
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["effect"], "allow")


class CreateFeatureTests(TestCase):
    def test_creates_feature_with_defaults(self):
        feature = services.create_feature(slug="ops.custom", label="Custom")
        self.assertTrue(feature.is_active)
        self.assertEqual(feature.required_permission, "")
