import uuid
from django.test import SimpleTestCase, override_settings

from apps.common.crypto import (
    TamperDetectedError,
    decrypt_user_secret,
    derive_user_key,
    encrypt_user_secret,
)


class CryptoTests(SimpleTestCase):
    @override_settings(
        TWO_FACTOR_ENCRYPTION_KEY="dGhpcy1pcy1hLXNhbXBsZS0zMi1ieXRlLWtleS0xMjM0NTY="
    )
    def test_encrypt_decrypt_roundtrip(self):
        user_id = uuid.uuid4()
        secret = "JBSWY3DPEHPK3PXP"
        email = "operator@ops.local"

        ciphertext = encrypt_user_secret(
            plaintext=secret, user_id=user_id, context=email
        )
        self.assertIsInstance(ciphertext, bytes)
        self.assertNotEqual(ciphertext.decode("latin1", errors="ignore"), secret)

        decrypted = decrypt_user_secret(
            ciphertext=ciphertext, user_id=user_id, context=email
        )
        self.assertEqual(decrypted, secret)

    @override_settings(
        TWO_FACTOR_ENCRYPTION_KEY="dGhpcy1pcy1hLXNhbXBsZS0zMi1ieXRlLWtleS0xMjM0NTY="
    )
    def test_derived_keys_differ_per_user(self):
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        key_a = derive_user_key(user_id=user_a, context="user@ops.local")
        key_b = derive_user_key(user_id=user_b, context="user@ops.local")
        self.assertNotEqual(key_a, key_b)

    @override_settings(
        TWO_FACTOR_ENCRYPTION_KEY="dGhpcy1pcy1hLXNhbXBsZS0zMi1ieXRlLWtleS0xMjM0NTY="
    )
    def test_cross_user_decryption_rejected(self):
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        secret = "SECRET123"

        ciphertext = encrypt_user_secret(
            plaintext=secret, user_id=user_a, context="a@ops.local"
        )
        with self.assertRaises(TamperDetectedError):
            decrypt_user_secret(
                ciphertext=ciphertext, user_id=user_b, context="b@ops.local"
            )

    @override_settings(
        TWO_FACTOR_ENCRYPTION_KEY="dGhpcy1pcy1hLXNhbXBsZS0zMi1ieXRlLWtleS0xMjM0NTY="
    )
    def test_tampered_ciphertext_rejected(self):
        user_id = uuid.uuid4()
        secret = "SECRET123"
        email = "test@ops.local"

        ciphertext = bytearray(
            encrypt_user_secret(plaintext=secret, user_id=user_id, context=email)
        )
        # Flip a byte in the ciphertext payload
        ciphertext[-5] ^= 0xFF

        with self.assertRaises(TamperDetectedError):
            decrypt_user_secret(
                ciphertext=bytes(ciphertext), user_id=user_id, context=email
            )
