from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts import selectors, services
from apps.accounts.models import User


class SuperadminGuardTests(TestCase):
    def test_cannot_delete_sole_superadmin(self):
        admin = services.register_user(
            email="admin@ops.local",
            password="Password!123456",
            is_staff=True,
            is_superuser=True,
        )
        self.assertEqual(selectors.count_active_superadmins(), 1)

        with self.assertRaises(ValidationError):
            services.delete_user(user=admin)

        # Ensure user was NOT deleted
        admin.refresh_from_db()
        self.assertFalse(admin.is_deleted)
        self.assertEqual(admin.status, User.Status.ACTIVE)

    def test_can_delete_superadmin_when_more_than_one_exists(self):
        admin1 = services.register_user(
            email="super1@ops.local",
            password="Password!123456",
            is_staff=True,
            is_superuser=True,
        )
        admin2 = services.register_user(
            email="super2@ops.local",
            password="Password!123456",
            is_staff=True,
            is_superuser=True,
        )
        self.assertEqual(selectors.count_active_superadmins(), 2)

        # Deleting admin2 should succeed
        services.delete_user(user=admin2, requested_by=admin1)
        admin2.refresh_from_db()
        self.assertTrue(admin2.is_deleted)
        self.assertEqual(admin2.status, User.Status.INACTIVE)
        self.assertFalse(admin2.is_active)
        self.assertEqual(admin2.deleted_by_id, admin1.pk)

        # Now only 1 superadmin remains, deleting admin1 must fail
        self.assertEqual(selectors.count_active_superadmins(), 1)
        with self.assertRaises(ValidationError):
            services.delete_user(user=admin1)

    def test_cannot_delete_admin_ops_local_as_sole_superadmin(self):
        admin = services.register_user(
            email="admin@ops.local",
            password="Password!123456",
            is_staff=True,
            is_superuser=True,
        )
        with self.assertRaises(ValidationError):
            services.delete_user(user=admin)

    def test_delete_normal_user_soft_deletes(self):
        staff = services.register_user(
            email="staff@ops.local",
            password="Password!123456",
            is_staff=True,
            is_superuser=False,
        )
        admin = services.register_user(
            email="admin@ops.local",
            password="Password!123456",
            is_staff=True,
            is_superuser=True,
        )
        services.delete_user(user=staff, requested_by=admin)

        staff.refresh_from_db()
        self.assertTrue(staff.is_deleted)
        self.assertEqual(staff.status, User.Status.INACTIVE)
        self.assertFalse(staff.is_active)
        self.assertIsNotNone(staff.deleted_at)
        self.assertEqual(staff.deleted_by_id, admin.pk)

        # Default manager excludes soft-deleted user
        self.assertIsNone(selectors.get_user_by_email("staff@ops.local"))
        # all_objects retains the record
        self.assertIsNotNone(User.all_objects.filter(email="staff@ops.local").first())
