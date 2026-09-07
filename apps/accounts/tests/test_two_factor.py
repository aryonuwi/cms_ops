import pyotp
from django.test import TestCase, override_settings

from apps.accounts import selectors, services
from apps.accounts.models import User, UserTwoFactor
from apps.common import crypto


@override_settings(
    TWO_FACTOR_ENCRYPTION_KEY="dGhpcy1pcy1hLXNhbXBsZS0zMi1ieXRlLWtleS0xMjM0NTY="
)
class TwoFactorTests(TestCase):
    def setUp(self):
        self.user = services.register_user(
            email="operator@ops.local",
            password="Password!123456",
            is_staff=True,
        )

    def test_setup_and_enable_two_factor(self):
        secret, uri = services.setup_two_factor(user=self.user)
        self.assertTrue(len(secret) >= 16)
        self.assertIn("otpauth://totp/", uri)

        # Record exists but not enabled yet
        self.assertFalse(selectors.is_two_factor_enabled(self.user))

        # Enable with valid code
        totp = pyotp.TOTP(secret)
        code = totp.now()

        ok = services.enable_two_factor(user=self.user, code=code)
        self.assertTrue(ok)
        self.assertTrue(selectors.is_two_factor_enabled(self.user))

        # Verify code
        self.assertTrue(services.verify_two_factor_code(user=self.user, code=code))
        self.assertFalse(services.verify_two_factor_code(user=self.user, code="000000"))

    def test_tampered_database_triggers_auto_reset(self):
        secret, _uri = services.setup_two_factor(user=self.user)
        code = pyotp.TOTP(secret).now()
        services.enable_two_factor(user=self.user, code=code)
        self.assertTrue(selectors.is_two_factor_enabled(self.user))

        # Attacker tampers directly with the database row
        u2f = UserTwoFactor.objects.get(user_id=self.user.pk)
        corrupted = bytearray(u2f.encrypted_secret)
        corrupted[-4] ^= 0xAA
        u2f.encrypted_secret = bytes(corrupted)
        u2f.save(update_fields=["encrypted_secret"])

        # Verifying should detect tampering, return False, and AUTO-RESET 2FA
        is_valid = services.verify_two_factor_code(user=self.user, code=code)
        self.assertFalse(is_valid)

        # 2FA must now be reset (disabled)
        self.assertFalse(selectors.is_two_factor_enabled(self.user))

    def test_disable_two_factor(self):
        secret, _uri = services.setup_two_factor(user=self.user)
        code = pyotp.TOTP(secret).now()
        services.enable_two_factor(user=self.user, code=code)
        self.assertTrue(selectors.is_two_factor_enabled(self.user))

        services.disable_two_factor(user=self.user)
        self.assertFalse(selectors.is_two_factor_enabled(self.user))
