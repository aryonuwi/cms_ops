"""Precedence matrix for action-level access: the single ``user_can`` gate."""

from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.test import TestCase

from apps.access import services as access_services
from apps.access.models import Action, Feature, FeatureGrant
from apps.access.selectors import user_can
from apps.accounts import services as accounts_services
from apps.common import events as bus

PASSWORD = "correct-horse-battery"


class UserCanMatrixTests(TestCase):
    def tearDown(self):
        bus.clear_subscribers()

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
        self.action = Action.objects.create(
            feature=self.feature,
            slug="reports.overview.create",
            code="create",
            label="Create report",
        )
        Action.objects.create(
            feature=self.feature,
            slug="reports.overview.approve",
            code="approve",
            label="Approve report",
        )
        self.view_user = Permission.objects.get(codename="view_user")

    def grant(self, *, grantee_type, group=None, user_id=None, org_unit=None, action=None, effect="allow"):
        return access_services.grant_feature(
            feature=self.feature,
            grantee_type=grantee_type,
            group=group,
            user_id=user_id,
            org_unit=org_unit,
            action=action,
            effect=effect,
        )

    def test_anonymous_and_inactive_denied(self):
        self.assertFalse(user_can(AnonymousUser(), self.action.slug))
        self.operator.is_active = False
        self.assertFalse(user_can(self.operator, self.action.slug))

    def test_superuser_allowed(self):
        self.assertTrue(user_can(self.superuser, self.action.slug))

    def test_unknown_or_inactive_action_denied(self):
        self.assertFalse(user_can(self.operator, "no.such_action"))
        self.action.is_active = False
        self.action.save()
        self.assertFalse(user_can(self.operator, self.action.slug))

    def test_default_deny(self):
        self.assertFalse(user_can(self.operator, self.action.slug))

    def test_action_group_allow(self):
        self.operator.groups.add(self.ops)
        self.grant(grantee_type="group", group=self.ops, action=self.action)
        self.assertTrue(user_can(self.operator, self.action.slug))

    def test_feature_level_group_allow_covers_all_actions(self):
        self.operator.groups.add(self.ops)
        self.grant(grantee_type="group", group=self.ops)  # feature-scoped
        self.assertTrue(user_can(self.operator, self.action.slug))
        self.assertTrue(user_can(self.operator, "reports.overview.approve"))

    def test_group_deny_beats_group_allow(self):
        self.operator.groups.add(self.ops)
        self.operator.groups.add(self.fin)
        self.grant(grantee_type="group", group=self.ops, action=self.action, effect="allow")
        self.grant(grantee_type="group", group=self.fin, action=self.action, effect="deny")
        self.assertFalse(user_can(self.operator, self.action.slug))

    def test_personal_allow_overrides_group_deny(self):
        self.operator.groups.add(self.ops)
        self.grant(grantee_type="group", group=self.ops, action=self.action, effect="deny")
        self.grant(grantee_type="user", user_id=self.operator.pk, action=self.action, effect="allow")
        self.assertTrue(user_can(self.operator, self.action.slug))

    def test_action_scope_beats_feature_scope(self):
        self.operator.groups.add(self.ops)
        self.grant(grantee_type="group", group=self.ops, effect="deny")  # feature-scoped deny
        self.grant(grantee_type="group", group=self.ops, action=self.action, effect="allow")
        self.assertTrue(user_can(self.operator, self.action.slug))

    def test_required_permission_gates_action(self):
        self.action.required_permission = "accounts.view_user"
        self.action.save()
        self.operator.groups.add(self.ops)
        self.grant(grantee_type="group", group=self.ops, action=self.action)

        # Group-granted but the underlying Django permission is missing.
        self.assertFalse(user_can(self.operator, self.action.slug))

        # Holding the permission through the same group closes the loop. The
        # operator is re-fetched because has_perm() caches on the instance.
        self.ops.permissions.add(self.view_user)
        operator = type(self.operator).objects.get(pk=self.operator.pk)
        self.assertTrue(user_can(operator, self.action.slug))

    def test_org_unit_grant_reaches_member(self):
        org = access_services.create_org_unit(name="Staff", slug="staff")
        access_services.add_org_member(org_unit=org, user_id=self.operator.pk)
        self.grant(grantee_type="org_unit", org_unit=org, action=self.action)
        self.assertTrue(user_can(self.operator, self.action.slug))

    def test_ancestor_org_unit_grant_reaches_descendant_member(self):
        company = access_services.create_org_unit(name="Company", slug="company")
        staff = access_services.create_org_unit(
            name="Staff", slug="staff", parent=company
        )
        access_services.add_org_member(org_unit=staff, user_id=self.operator.pk)
        self.grant(grantee_type="org_unit", org_unit=company, action=self.action)
        self.assertTrue(user_can(self.operator, self.action.slug))

    def test_org_unit_deny_beats_group_allow(self):
        org = access_services.create_org_unit(name="Staff", slug="staff")
        access_services.add_org_member(org_unit=org, user_id=self.operator.pk)
        self.operator.groups.add(self.ops)
        self.grant(grantee_type="group", group=self.ops, action=self.action, effect="allow")
        self.grant(grantee_type="org_unit", org_unit=org, action=self.action, effect="deny")
        self.assertFalse(user_can(self.operator, self.action.slug))

    def test_action_grant_does_not_leak_to_sibling_action(self):
        self.operator.groups.add(self.ops)
        self.grant(grantee_type="group", group=self.ops, action=self.action)
        self.assertTrue(user_can(self.operator, self.action.slug))
        self.assertFalse(user_can(self.operator, "reports.overview.approve"))

    def test_action_grant_publishes_action_granted(self):
        received = []
        bus.subscribe("access.action_granted", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            self.grant(grantee_type="group", group=self.ops, action=self.action)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["action_slug"], "reports.overview.create")

    def test_feature_grant_publishes_feature_granted(self):
        received = []
        bus.subscribe("access.feature_granted", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            self.grant(grantee_type="group", group=self.ops)
        self.assertEqual(len(received), 1)


class GrantModuleTests(TestCase):
    def setUp(self):
        self.ops = Group.objects.create(name="ops")
        Feature.objects.create(slug="reports.a", label="A", module="reports")
        Feature.objects.create(slug="reports.b", label="B", module="reports")
        Feature.objects.create(slug="other.c", label="C", module="other")

    def test_grants_every_feature_under_module_only(self):
        count = access_services.grant_module(
            module_slug="reports", grantee_type="group", group=self.ops
        )
        self.assertEqual(count, 2)
        self.assertEqual(
            FeatureGrant.objects.filter(feature__module="reports").count(), 2
        )
        self.assertEqual(
            FeatureGrant.objects.filter(feature__module="other").count(), 0
        )
