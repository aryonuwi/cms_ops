"""The access admins stay superuser-only at the URL level."""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase

from apps.access import services
from apps.access.admin import FeatureGrantAdmin, FeatureGrantForm
from apps.access.models import Feature, FeatureGrant
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


class FeatureGrantAdminEditTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.superuser = accounts_services.register_user(
            email="root@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.group = Group.objects.create(name="Operators")
        services.sync_catalog()
        self.feature = Feature.objects.get(slug="accounts.users")
        self.other_feature = Feature.objects.get(slug="access.modules")

    def test_editing_grant_target_revokes_old_row(self):
        grant = services.grant_feature(
            feature=self.feature,
            grantee_type=FeatureGrant.GranteeType.GROUP,
            group=self.group,
        )
        old_grant_id = grant.pk
        admin_instance = FeatureGrantAdmin(FeatureGrant, self.site)
        request = self.factory.post("/admin/access/featuregrant/")
        request.user = self.superuser
        form = FeatureGrantForm(
            data={
                "feature": str(self.other_feature.pk),
                "action": "",
                "grantee_type": FeatureGrant.GranteeType.GROUP,
                "group": str(self.group.pk),
                "user": "",
                "org_unit": "",
                "effect": FeatureGrant.Effect.ALLOW,
            },
            instance=grant,
        )
        self.assertTrue(form.is_valid(), form.errors)
        changed = form.save(commit=False)

        admin_instance.save_model(request, changed, form, change=True)

        old_grant = FeatureGrant.all_objects.get(pk=old_grant_id)
        self.assertTrue(old_grant.is_deleted)
        self.assertFalse(
            FeatureGrant.objects.filter(
                feature=self.feature,
                group=self.group,
                action__isnull=True,
            ).exists()
        )
        self.assertTrue(
            FeatureGrant.objects.filter(
                feature=self.other_feature,
                group=self.group,
                action__isnull=True,
            ).exists()
        )
