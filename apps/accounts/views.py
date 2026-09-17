"""Views for account recovery and Two-Factor Authentication (2FA)."""

from django.contrib.auth.tokens import default_token_generator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import gettext_lazy as _

from . import selectors, services
from .forms import PasswordResetConfirmForm, TwoFactorVerifyForm


def password_reset_confirm_view(request, uidb64: str, token: str):
    """Accept a one-time email token and delegate the password write to a service."""
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = selectors.get_user_by_id(user_id)
    except (TypeError, ValueError, OverflowError):
        user = None

    valid_link = user is not None and default_token_generator.check_token(user, token)
    if not valid_link:
        return render(
            request,
            "accounts/password_reset_invalid.html",
            status=400,
        )

    if request.method == "POST":
        form = PasswordResetConfirmForm(request.POST, user=user)
        if form.is_valid():
            try:
                services.reset_password_from_token(
                    user=user,
                    token=token,
                    new_password=form.cleaned_data["new_password"],
                )
            except ValidationError:
                return render(
                    request,
                    "accounts/password_reset_invalid.html",
                    status=400,
                )
            return render(request, "accounts/password_reset_complete.html")
    else:
        form = PasswordResetConfirmForm(user=user)

    return render(
        request,
        "accounts/password_reset_confirm.html",
        {"form": form, "email": user.email},
    )


@login_required
def two_factor_verify_view(request):
    """Challenge view prompting for 6-digit TOTP code when 2FA is enabled."""
    if not selectors.is_two_factor_enabled(request.user):
        request.session["two_factor_verified"] = True
        next_url = request.GET.get("next") or "/admin/"
        return redirect(next_url)

    if request.method == "POST":
        form = TwoFactorVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            is_valid = services.verify_two_factor_code(user=request.user, code=code)
            if is_valid:
                request.session["two_factor_verified"] = True
                messages.success(request, _("Verifikasi 2FA berhasil. Selamat datang!"))
                next_url = request.GET.get("next") or "/admin/"
                return redirect(next_url)
            else:
                form.add_error(
                    "code",
                    _(
                        "Kode verifikasi salah, telah kedaluwarsa, atau 2FA telah di-reset karena anomali data."
                    ),
                )
    else:
        form = TwoFactorVerifyForm()

    context = {
        "form": form,
        "email": request.user.email,
        "next": request.GET.get("next", "/admin/"),
    }
    return render(request, "accounts/two_factor_verify.html", context)


@login_required
def two_factor_setup_view(request):
    """Setup view displaying the secret key and verifying the initial code to enable 2FA."""
    if request.method == "POST":
        form = TwoFactorVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            enabled = services.enable_two_factor(user=request.user, code=code)
            if enabled:
                request.session["two_factor_verified"] = True
                messages.success(
                    request,
                    _("Autentikasi Dua Langkah (2FA) Google Authenticator berhasil diaktifkan."),
                )
                return redirect("/admin/")
            else:
                form.add_error(
                    "code",
                    _(
                        "Kode verifikasi 6 digit tidak cocok. Silakan pastikan jam pada perangkat Anda sinkron."
                    ),
                )
    else:
        form = TwoFactorVerifyForm()

    secret, otpauth_uri = services.setup_two_factor(user=request.user)
    context = {
        "form": form,
        "secret": secret,
        "otpauth_uri": otpauth_uri,
        "email": request.user.email,
    }
    return render(request, "accounts/two_factor_setup.html", context)
