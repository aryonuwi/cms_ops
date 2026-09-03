from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts import selectors, services
from apps.common import events as bus

User = get_user_model()


class RegisterUserTests(TestCase):
    def tearDown(self):
        bus.clear_subscribers()

    def test_creates_user_with_normalised_email(self):
        user = services.register_user(
            email="  Ops.Lead@Example.COM ", password="correct-horse-battery"
        )
        self.assertEqual(user.email, "ops.lead@example.com")
        self.assertTrue(user.check_password("correct-horse-battery"))

    def test_rejects_weak_password(self):
        with self.assertRaises(ValidationError):
            services.register_user(email="weak@example.com", password="12345")
        self.assertIsNone(selectors.get_user_by_email("weak@example.com"))

    def test_publishes_event_after_commit(self):
        received = []
        bus.subscribe("accounts.user_registered", received.append)

        with self.captureOnCommitCallbacks(execute=True):
            services.register_user(
                email="watched@example.com", password="correct-horse-battery"
            )

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["email"], "watched@example.com")


class DeactivateUserTests(TestCase):
    def tearDown(self):
        bus.clear_subscribers()

    def test_keeps_row_and_blocks_login(self):
        user = services.register_user(
            email="leaver@example.com", password="correct-horse-battery"
        )
        services.deactivate_user(user=user)

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(user.status, User.Status.INACTIVE)
        self.assertEqual(User.objects.filter(pk=user.pk).count(), 1)
        self.assertNotIn(user, selectors.list_active_users())


class StatusTransitionTests(TestCase):
    def setUp(self):
        self.user = services.register_user(
            email="target@example.com", password="correct-horse-battery"
        )

    def tearDown(self):
        bus.clear_subscribers()

    def test_activate_sets_status_and_is_active(self):
        services.suspend_user(user=self.user)

        received = []
        bus.subscribe("accounts.user_activated", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.activate_user(user=self.user)

        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.ACTIVE)
        self.assertTrue(self.user.is_active)
        self.assertEqual(len(received), 1)

    def test_activate_is_idempotent(self):
        services.suspend_user(user=self.user)
        received = []
        bus.subscribe("accounts.user_activated", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.activate_user(user=self.user)
            services.activate_user(user=self.user)
        self.assertEqual(len(received), 1)

    def test_suspend_sets_status_and_is_active(self):
        received = []
        bus.subscribe("accounts.user_suspended", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.suspend_user(user=self.user)

        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.SUSPENDED)
        self.assertFalse(self.user.is_active)
        self.assertEqual(len(received), 1)

    def test_suspend_is_idempotent(self):
        received = []
        bus.subscribe("accounts.user_suspended", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.suspend_user(user=self.user)
            services.suspend_user(user=self.user)
        self.assertEqual(len(received), 1)

    def test_deactivate_sets_status_and_is_active(self):
        received = []
        bus.subscribe("accounts.user_deactivated", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.deactivate_user(user=self.user)

        self.user.refresh_from_db()
        self.assertEqual(self.user.status, User.Status.INACTIVE)
        self.assertFalse(self.user.is_active)
        self.assertEqual(len(received), 1)

    def test_deactivate_is_idempotent(self):
        services.deactivate_user(user=self.user)
        received = []
        bus.subscribe("accounts.user_deactivated", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.deactivate_user(user=self.user)
        self.assertEqual(len(received), 0)

    def test_suspend_blocks_login(self):
        services.suspend_user(user=self.user)
        self.assertIsNone(
            authenticate(email="target@example.com", password="correct-horse-battery")
        )


class UpdateUserTests(TestCase):
    def setUp(self):
        self.user = services.register_user(
            email="orig@example.com", password="correct-horse-battery"
        )

    def tearDown(self):
        bus.clear_subscribers()

    def test_updates_names_and_publishes_event(self):
        received = []
        bus.subscribe("accounts.user_updated", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.update_user(
                user=self.user, first_name="Ada", last_name="Lovelace"
            )

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Ada")
        self.assertEqual(self.user.last_name, "Lovelace")
        self.assertEqual(len(received), 1)

    def test_normalises_email(self):
        services.update_user(user=self.user, email="  NEW.Address@Example.COM ")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new.address@example.com")

    def test_rejects_duplicate_email(self):
        services.register_user(
            email="taken@example.com", password="correct-horse-battery"
        )
        with self.assertRaises(ValueError):
            services.update_user(user=self.user, email="taken@example.com")

    def test_no_change_publishes_no_event(self):
        received = []
        bus.subscribe("accounts.user_updated", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.update_user(user=self.user)
        self.assertEqual(len(received), 0)


class GroupAndPermissionTests(TestCase):
    def setUp(self):
        self.user = services.register_user(
            email="member@example.com", password="correct-horse-battery"
        )
        self.group = Group.objects.create(name="Operators")
        self.permission = Permission.objects.filter(
            content_type__app_label="accounts", codename="view_user"
        ).first()

    def tearDown(self):
        bus.clear_subscribers()

    def test_assign_group(self):
        received = []
        bus.subscribe("accounts.group_assigned", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.assign_group(user=self.user, group=self.group)

        self.user.refresh_from_db()
        self.assertIn(self.group, self.user.groups.all())
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["group_id"], str(self.group.pk))

    def test_assign_group_is_idempotent(self):
        received = []
        bus.subscribe("accounts.group_assigned", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.assign_group(user=self.user, group=self.group)
            services.assign_group(user=self.user, group=self.group)
        self.assertEqual(len(received), 1)

    def test_unassign_group(self):
        services.assign_group(user=self.user, group=self.group)

        received = []
        bus.subscribe("accounts.group_unassigned", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.unassign_group(user=self.user, group=self.group)

        self.user.refresh_from_db()
        self.assertNotIn(self.group, self.user.groups.all())
        self.assertEqual(len(received), 1)

    def test_unassign_group_is_idempotent(self):
        received = []
        bus.subscribe("accounts.group_unassigned", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.unassign_group(user=self.user, group=self.group)
            services.unassign_group(user=self.user, group=self.group)
        self.assertEqual(len(received), 0)

    def test_grant_permission(self):
        received = []
        bus.subscribe("accounts.permission_granted", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.grant_permission(user=self.user, permission=self.permission)

        self.user.refresh_from_db()
        self.assertIn(self.permission, self.user.user_permissions.all())
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["permission_codename"], "view_user")

    def test_grant_permission_is_idempotent(self):
        received = []
        bus.subscribe("accounts.permission_granted", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.grant_permission(user=self.user, permission=self.permission)
            services.grant_permission(user=self.user, permission=self.permission)
        self.assertEqual(len(received), 1)

    def test_revoke_permission(self):
        services.grant_permission(user=self.user, permission=self.permission)

        received = []
        bus.subscribe("accounts.permission_revoked", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.revoke_permission(user=self.user, permission=self.permission)

        self.user.refresh_from_db()
        self.assertNotIn(self.permission, self.user.user_permissions.all())
        self.assertEqual(len(received), 1)

    def test_revoke_permission_is_idempotent(self):
        received = []
        bus.subscribe("accounts.permission_revoked", received.append)
        with self.captureOnCommitCallbacks(execute=True):
            services.revoke_permission(user=self.user, permission=self.permission)
            services.revoke_permission(user=self.user, permission=self.permission)
        self.assertEqual(len(received), 0)


class SuperuserTests(TestCase):
    def test_requires_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(email="", password="x")
