"""The organisation tree: structure, cycle guard and membership ancestry."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.access import services
from apps.access.models import OrgUnitMembership
from apps.access.selectors import effective_org_unit_ids, list_org_unit_member_ids
from apps.accounts import services as accounts_services
from apps.common import events as bus

PASSWORD = "correct-horse-battery"


class OrgUnitTests(TestCase):
    def tearDown(self):
        bus.clear_subscribers()

    def setUp(self):
        self.company = services.create_org_unit(name="Company", slug="company")
        self.manager = services.create_org_unit(
            name="Manager", slug="manager", parent=self.company
        )
        self.supervisor = services.create_org_unit(
            name="Supervisor", slug="supervisor", parent=self.manager
        )
        self.staff = services.create_org_unit(
            name="Staff", slug="staff", parent=self.supervisor
        )
        self.user = accounts_services.register_user(
            email="staff@example.com", password=PASSWORD
        )

    def test_create_publishes_org_unit_created(self):
        received = []
        bus.subscribe("access.org_unit_created", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.create_org_unit(name="New", slug="new")

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["org_unit_slug"], "new")
        self.assertIsNone(received[0].payload["parent_slug"])

    def test_move_rejects_cycles(self):
        with self.assertRaises(ValueError):
            services.move_org_unit(org_unit=self.company, new_parent=self.staff)

    def test_move_publishes_event(self):
        received = []
        bus.subscribe("access.org_unit_moved", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.move_org_unit(org_unit=self.staff, new_parent=self.company)

        self.staff.refresh_from_db()
        self.assertEqual(self.staff.parent, self.company)
        self.assertEqual(received[0].payload["parent_slug"], "company")

    def test_add_member_publishes_only_on_real_change(self):
        received = []
        bus.subscribe("access.org_unit_member_added", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.add_org_member(org_unit=self.staff, user_id=self.user.pk)
        with self.captureOnCommitCallbacks(execute=True):
            services.add_org_member(org_unit=self.staff, user_id=self.user.pk)

        self.assertEqual(len(received), 1)
        self.assertEqual(OrgUnitMembership.objects.count(), 1)

    def test_remove_member_publishes_previous_state(self):
        membership = services.add_org_member(org_unit=self.staff, user_id=self.user.pk)
        received = []
        bus.subscribe("access.org_unit_member_removed", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.remove_org_member(membership=membership)

        self.assertFalse(OrgUnitMembership.objects.filter(pk=membership.pk).exists())
        self.assertEqual(received[0].payload["org_unit_slug"], "staff")
        self.assertEqual(received[0].payload["user_id"], str(self.user.pk))

    def test_effective_org_unit_ids_include_ancestors(self):
        services.add_org_member(org_unit=self.staff, user_id=self.user.pk)
        ids = effective_org_unit_ids(self.user)
        expected = {
            self.staff.pk,
            self.supervisor.pk,
            self.manager.pk,
            self.company.pk,
        }
        self.assertEqual(ids, expected)

    def test_effective_org_unit_ids_empty_for_non_member(self):
        self.assertEqual(effective_org_unit_ids(self.user), set())

    def test_list_org_unit_member_ids(self):
        services.add_org_member(org_unit=self.staff, user_id=self.user.pk)
        self.assertEqual(list_org_unit_member_ids(self.staff), {self.user.pk})

    def test_database_rejects_duplicate_membership(self):
        services.add_org_member(org_unit=self.staff, user_id=self.user.pk)
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                OrgUnitMembership.objects.create(
                    org_unit=self.staff, user_id=self.user.pk
                )
