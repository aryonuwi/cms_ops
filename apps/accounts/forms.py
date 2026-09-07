"""Forms for accounts module: credentials editing and 2FA authentication."""

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from unfold.forms import UserChangeForm

from . import selectors
from .models import User


class CustomUserChangeForm(UserChangeForm):
    """Admin change form allowing inline email and password updates."""

    email = forms.EmailField(
        label=_("Alamat Email"),
        help_text=_("Alamat email unik akun. Digunakan untuk login ke sistem."),
        required=True,
    )
    new_password = forms.CharField(
        label=_("Password Baru"),
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}),
        help_text=_("Biarkan kosong jika tidak ingin mengubah password akun ini."),
    )
    confirm_new_password = forms.CharField(
        label=_("Konfirmasi Password Baru"),
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}),
        help_text=_("Ketik ulang password baru untuk memastikan tidak ada kesalahan."),
    )

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise ValidationError(_("Email wajib diisi."))
        existing = selectors.get_user_by_email(email)
        if existing and existing.pk != self.instance.pk:
            raise ValidationError(_("Email ini sudah digunakan oleh akun lain."))
        return email

    def clean(self):
        cleaned_data = super().clean()
        new_pw = cleaned_data.get("new_password")
        confirm_pw = cleaned_data.get("confirm_new_password")

        if new_pw or confirm_pw:
            if new_pw != confirm_pw:
                raise ValidationError(
                    {"confirm_new_password": _("Konfirmasi password baru tidak cocok.")}
                )
            # Validate against password policy
            validate_password(new_pw, self.instance)

        return cleaned_data


class TwoFactorVerifyForm(forms.Form):
    """Challenge form for verifying Google Authenticator 6-digit TOTP code."""

    code = forms.CharField(
        max_length=6,
        min_length=6,
        label=_("Kode Verifikasi Google Authenticator"),
        help_text=_("Masukkan 6 digit angka yang muncul pada aplikasi Google Authenticator Anda."),
        widget=forms.TextInput(
            attrs={
                "class": "border border-gray-300 rounded-md p-2 w-full text-center text-2xl tracking-widest font-mono",
                "placeholder": "000000",
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": "[0-9]*",
                "autofocus": "autofocus",
            }
        ),
    )

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip()
        if not code.isdigit() or len(code) != 6:
            raise ValidationError(_("Kode verifikasi harus berupa 6 digit angka."))
        return code
