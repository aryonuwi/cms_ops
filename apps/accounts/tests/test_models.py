from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class UserStatusInvariantTests(TestCase):
    def test_save_derives_is_active_from_status(self):
        user = User.objects.create_user(email="s@example.com", password="pw")
        user.status = User.Status.SUSPENDED
        user.save()

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(user.status, User.Status.SUSPENDED)

    def test_create_user_inactive_flag_maps_to_inactive_status(self):
        user = User.objects.create_user(
            email="i@example.com", password="pw", is_active=False
        )

        self.assertEqual(user.status, User.Status.INACTIVE)
        self.assertFalse(user.is_active)

        user.refresh_from_db()
        self.assertEqual(user.status, User.Status.INACTIVE)
        self.assertFalse(user.is_active)
