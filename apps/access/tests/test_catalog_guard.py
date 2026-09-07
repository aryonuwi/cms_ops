from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase

from apps.access import services
from apps.access.admin import (
    ActionAdmin,
    FeatureAdmin,
    FeatureGrantForm,
    ModuleAdmin,
)
from apps.access.models import Action, Feature, FeatureGrant, Module, OrgUnit, OrgUnitMembership
from apps.accounts import services as account_services


class CatalogGuardAndDynamicActionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.superuser = account_services.register_user(
            email="super@ops.local",
            password="Password!123456",
            is_staff=True,
            is_superuser=True,
        )
        self.module = services.create_module(slug="testmod", label="Test Module")
        self.feature = Feature.objects.create(slug="testfeat", label="Test Feature", module="testmod")
        self.action = services.create_action(feature=self.feature, code="view", label="View")

    def test_catalog_admins_disallow_manual_add(self):
        request = self.factory.get("/admin/")
        request.user = self.superuser

        mod_admin = ModuleAdmin(Module, self.site)
        feat_admin = FeatureAdmin(Feature, self.site)
        act_admin = ActionAdmin(Action, self.site)

        self.assertFalse(mod_admin.has_add_permission(request))
        self.assertFalse(feat_admin.has_add_permission(request))
        self.assertFalse(act_admin.has_add_permission(request))

        self.assertFalse(mod_admin.has_delete_permission(request))
        self.assertFalse(feat_admin.has_delete_permission(request))
        self.assertFalse(act_admin.has_delete_permission(request))

    def test_dynamic_action_widget_data_feature_attribute(self):
        form = FeatureGrantForm()
        action_field = form.fields["action"]
        widget = action_field.widget

        # Render option for self.action
        option = widget.create_option(
            name="action",
            value=self.action.pk,
            label="View",
            selected=False,
            index=1,
        )
        self.assertIn("data-feature", option["attrs"])
        self.assertEqual(option["attrs"]["data-feature"], str(self.feature.pk))

    def test_soft_deleted_grant_reactivates_cleanly(self):
        group = Group.objects.create(name="Support Team")
        grant = services.grant_feature(
            feature=self.feature,
            grantee_type=FeatureGrant.GranteeType.GROUP,
            group=group,
            action=self.action,
        )
        self.assertFalse(grant.is_deleted)

        # Revoke (soft-delete)
        services.revoke_feature(grant=grant)
        grant.refresh_from_db()
        self.assertTrue(grant.is_deleted)
        self.assertFalse(FeatureGrant.objects.filter(pk=grant.pk).exists())

        # Grant again: must reactivate the soft-deleted row without unique constraint error
        re_grant = services.grant_feature(
            feature=self.feature,
            grantee_type=FeatureGrant.GranteeType.GROUP,
            group=group,
            action=self.action,
        )
        self.assertEqual(re_grant.pk, grant.pk)
        self.assertFalse(re_grant.is_deleted)
        self.assertTrue(FeatureGrant.objects.filter(pk=grant.pk).exists())

    def test_soft_deleted_org_member_reactivates_cleanly(self):
        org = services.create_org_unit(name="Operations", slug="ops")
        member = services.add_org_member(org_unit=org, user_id=str(self.superuser.pk))
        self.assertFalse(member.is_deleted)

        # Remove member (soft-delete)
        services.remove_org_member(membership=member)
        member.refresh_from_db()
        self.assertTrue(member.is_deleted)

        # Add member again: must reactivate without error
        re_member = services.add_org_member(org_unit=org, user_id=str(self.superuser.pk))
        self.assertEqual(re_member.pk, member.pk)
        self.assertFalse(re_member.is_deleted)
        self.assertTrue(OrgUnitMembership.objects.filter(pk=member.pk).exists())
