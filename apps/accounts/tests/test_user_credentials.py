from django.contrib.auth import authenticate
from django.test import TestCase

from apps.accounts import services


class UserCredentialsTests(TestCase):
    def test_update_email_and_password(self):
        user = services.register_user(
            email="original@ops.local",
            password="OldPassword!123",
            is_staff=True,
        )

        # Update email and change password
        services.update_user(
            user=user,
            email="NEW.EMAIL@ops.local",
            new_password="NewPassword!999",
            first_name="John",
            last_name="Doe",
        )

        user.refresh_from_db()
        self.assertEqual(user.email, "new.email@ops.local")
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")

        # Verify old password fails, new password works
        self.assertIsNone(
            authenticate(email="new.email@ops.local", password="OldPassword!123")
        )
        auth_user = authenticate(
            email="new.email@ops.local", password="NewPassword!999"
        )
        self.assertIsNotNone(auth_user)
        self.assertEqual(auth_user.pk, user.pk)

    def test_cannot_update_to_existing_email(self):
        services.register_user(
            email="user1@ops.local",
            password="Password!123",
        )
        user2 = services.register_user(
            email="user2@ops.local",
            password="Password!123",
        )

        with self.assertRaises(ValueError):
            services.update_user(user=user2, email="user1@ops.local")
