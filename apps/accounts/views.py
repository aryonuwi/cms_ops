"""Views for Two-Factor Authentication (2FA) via Google Authenticator."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from . import selectors, services
from .forms import TwoFactorVerifyForm


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
