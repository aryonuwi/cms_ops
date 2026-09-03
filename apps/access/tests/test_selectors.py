"""Precedence matrix for the single point where menu access is decided.

Every rule documented on ``selectors.user_can_access`` gets a case here, so
the fail-closed behaviour can never silently change.
"""

from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.test import TestCase

from apps.access import services as access_services
from apps.access.models import Feature
from apps.access.selectors import effective_features, user_can_access
from apps.accounts import services as accounts_services

PASSWORD = "correct-horse-battery"


class AccessMatrixTests(TestCase):
    def setUp(self):
        self.ops = Group.objects.create(name="ops")
        self.fin = Group.objects.create(name="fin")

        self.superuser = accounts_services.register_user(
            email="root@example.com", password=PASSWORD
        )
        self.superuser.is_superuser = True
        self.superuser.is_staff = True
        self.superuser.save()

        self.operator = accounts_services.register_user(
            email="op@example.com", password=PASSWORD, is_staff=True
        )

        self.feature = Feature.objects.create(slug="reports.overview", label="Overview")
        Feature.objects.create(slug="reports.retired", label="Retired", is_active=False)
        Feature.objects.create(
            slug="reports.permgated",
            label="Permission-gated",
            required_permission="accounts.view_user",
        )
        self.view_user = Permission.objects.get(codename="view_user")

    def grant_group(self, group, effect="allow", feature=None):
        return access_services.grant_feature(
            feature=feature or self.feature,
            grantee_type="group",
            group=group,
            effect=effect,
        )

    def grant_personal(self, user, effect="allow", feature=None):
        return access_services.grant_feature(
            feature=feature or self.feature,
            grantee_type="user",
            user_id=user.pk,
            effect=effect,
        )

    def test_anonymous_and_inactive_users_are_denied_everything(self):
        self.assertFalse(user_can_access(AnonymousUser(), self.feature.slug))
        self.assertFalse(effective_features(AnonymousUser()))

        self.operator.is_active = False
        self.assertFalse(user_can_access(self.operator, self.feature.slug))

    def test_superuser_bypasses_grants(self):
        self.assertTrue(user_can_access(self.superuser, self.feature.slug))
        self.assertTrue(
            user_can_access(self.superuser, "reports.permgated")
        )  # superusers hold every permission

    def test_unknown_or_inactive_feature_is_denied(self):
        self.assertFalse(user_can_access(self.operator, "no.such_feature"))
        self.assertFalse(user_can_access(self.operator, "reports.retired"))

    def test_no_grants_means_default_deny(self):
        self.assertFalse(user_can_access(self.operator, self.feature.slug))

    def test_group_allow_grants_access(self):
        self.operator.groups.add(self.ops)
        self.grant_group(self.ops)
        self.assertTrue(user_can_access(self.operator, self.feature.slug))

    def test_group_deny_beats_group_allow(self):
        self.operator.groups.add(self.ops)
        self.operator.groups.add(self.fin)
        self.grant_group(self.ops, effect="allow")
        self.grant_group(self.fin, effect="deny")
        self.assertFalse(user_can_access(self.operator, self.feature.slug))

    def test_personal_allow_overrides_group_deny(self):
        self.operator.groups.add(self.ops)
        self.grant_group(self.ops, effect="deny")
        self.grant_personal(self.operator, effect="allow")
        self.assertTrue(user_can_access(self.operator, self.feature.slug))

    def test_personal_deny_beats_group_allow(self):
        self.operator.groups.add(self.ops)
        self.grant_group(self.ops, effect="allow")
        self.grant_personal(self.operator, effect="deny")
        self.assertFalse(user_can_access(self.operator, self.feature.slug))

    def test_personal_allow_without_any_group_grant(self):
        self.grant_personal(self.operator, effect="allow")
        self.assertTrue(user_can_access(self.operator, self.feature.slug))

    def test_required_permission_gates_visibility(self):
        self.operator.groups.add(self.ops)
        self.grant_group(self.ops, feature=Feature.objects.get(slug="reports.permgated"))

        # Group-granted but the underlying Django permission is missing.
        self.assertFalse(user_can_access(self.operator, "reports.permgated"))

        # Holding the permission through the same group closes the loop. The
        # operator is re-fetched because has_perm() caches on the instance.
        self.ops.permissions.add(self.view_user)
        operator = type(self.operator).objects.get(pk=self.operator.pk)
        self.assertTrue(user_can_access(operator, "reports.permgated"))

    def test_effective_features_never_drifts_from_user_can_access(self):
        self.operator.groups.add(self.ops)
        self.operator.groups.add(self.fin)
        self.grant_group(self.ops, effect="allow")
        self.grant_group(self.fin, effect="deny")
        self.grant_personal(self.operator, effect="allow")

        slugs = {f.slug for f in Feature.objects.filter(is_active=True)}
        expected = {s for s in slugs if user_can_access(self.operator, s)}
        self.assertEqual(effective_features(self.operator), expected)

        expected = {s for s in slugs if user_can_access(self.superuser, s)}
        self.assertEqual(effective_features(self.superuser), expected)
