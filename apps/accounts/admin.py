"""Unfold-styled admin for the accounts module."""

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.forms import AdminPasswordChangeForm, UserCreationForm

from apps.access import selectors as access_selectors
from apps.common.admin import BaseModelAdmin

from . import selectors as accounts_selectors
from . import services
from .forms import CustomUserChangeForm
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin, BaseModelAdmin):
    form = CustomUserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "status",
        "two_factor_badge",
    )
    list_filter = ("status", "is_staff", "is_superuser", "groups")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    filter_horizontal = ("groups", "user_permissions")

    # `is_active` is derived from `status` in `User.save()`, so the enum field
    # is what gets shown and edited here.
    readonly_fields = (
        "effective_access_summary",
        "two_factor_badge",
        "created_at",
        "updated_at",
        "created_by_id",
        "updated_by_id",
    )

    fieldsets = (
        (
            _("Kredensial Akun"),
            {
                "fields": ("email", "password", "new_password", "confirm_new_password"),
                "description": _(
                    "Alamat email dan password login. Anda dapat mengubah password secara langsung dengan mengisi field Password Baru di bawah."
                ),
            },
        ),
        (
            _("Informasi Pengguna"),
            {
                "fields": ("first_name", "last_name"),
                "description": _("Nama depan dan belakang pengguna."),
            },
        ),
        (
            _("Hak Akses & Status"),
            {
                "fields": (
                    "status",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
                "description": _(
                    "Pengaturan status akun (Aktif/Nonaktif/Ditangguhkan) dan grup role. User mewarisi hak akses fitur dari grup yang diikutinya."
                ),
            },
        ),
        (
            _("Keamanan 2FA (Google Authenticator)"),
            {
                "fields": ("two_factor_badge",),
                "description": _(
                    "Status Autentikasi Dua Langkah. Jika aktif, token disimpan dalam database dengan enkripsi simetris dinamis."
                ),
            },
        ),
        (
            _("Jejak Audit & Tanggal"),
            {
                "classes": ("collapse",),
                "fields": (
                    "last_login",
                    "date_joined",
                    "created_at",
                    "created_by_id",
                    "updated_at",
                    "updated_by_id",
                ),
            },
        ),
        (_("Ringkasan Akses Efektif"), {"fields": ("effective_access_summary",)}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "usable_password", "password1", "password2"),
            },
        ),
    )

    actions = ["reset_two_factor_action"]

    @admin.action(description=_("Reset / Nonaktifkan 2FA untuk pengguna yang dipilih"))
    def reset_two_factor_action(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(
                request,
                _("Hanya superadmin yang dapat mereset 2FA pengguna."),
                messages.ERROR,
            )
            return
        count = 0
        for user in queryset:
            services.disable_two_factor(user=user, requested_by=request.user)
            count += 1
        self.message_user(
            request,
            _(f"2FA berhasil di-reset untuk {count} pengguna."),
            messages.SUCCESS,
        )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        # Only a superuser may hand out staff/superuser rights, manage groups
        # and permissions, or change an account's status.
        if not request.user.is_superuser:
            readonly += ["is_staff", "is_superuser", "user_permissions", "groups", "status"]
        return readonly

    # Enforcement (ADR-016): Single gate combining grants, org units and Django permissions.
    def has_module_permission(self, request):
        return access_selectors.user_can(request.user, "accounts.users.view")

    def has_view_permission(self, request, obj=None):
        return access_selectors.user_can(request.user, "accounts.users.view")

    def has_add_permission(self, request):
        return access_selectors.user_can(request.user, "accounts.users.create")

    def has_change_permission(self, request, obj=None):
        return access_selectors.user_can(request.user, "accounts.users.edit")

    def has_delete_permission(self, request, obj=None):
        # Superadmin deletion protection guard:
        # A superadmin cannot be deleted if active superadmin count <= 1.
        # admin@ops.local cannot be deleted unless another active superadmin exists.
        if not access_selectors.user_can(request.user, "accounts.users.delete"):
            return False
        if obj is not None and obj.is_superuser:
            superadmin_count = accounts_selectors.count_active_superadmins()
            if superadmin_count <= 1:
                return False
            if obj.email.lower() == "admin@ops.local" and superadmin_count <= 1:
                return False
        return True

    def save_model(self, request, obj, form, change):
        # R5: delegate credential changes through services.py
        if change and form:
            new_pw = form.cleaned_data.get("new_password")
            email = form.cleaned_data.get("email")
            first_name = form.cleaned_data.get("first_name")
            last_name = form.cleaned_data.get("last_name")

            services.update_user(
                user=obj,
                first_name=first_name,
                last_name=last_name,
                email=email,
                new_password=new_pw,
                updated_by_id=request.user.pk,
            )

            if request.user.is_superuser:
                status = form.cleaned_data.get("status")
                if status is not None and status != obj.status:
                    if status == User.Status.ACTIVE:
                        services.activate_user(user=obj)
                    elif status == User.Status.SUSPENDED:
                        services.suspend_user(user=obj)
                    else:
                        services.deactivate_user(user=obj)
                is_staff = form.cleaned_data.get("is_staff")
                if is_staff is not None and is_staff != obj.is_staff:
                    obj.is_staff = is_staff
                    obj.save(update_fields=["is_staff"])
                is_superuser = form.cleaned_data.get("is_superuser")
                if is_superuser is not None and is_superuser != obj.is_superuser:
                    obj.is_superuser = is_superuser
                    obj.save(update_fields=["is_superuser"])
        else:
            if not getattr(obj, "created_by_id", None):
                obj.created_by_id = request.user.pk
            obj.updated_by_id = request.user.pk
            super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        services.delete_user(user=obj, requested_by=request.user)

    def delete_queryset(self, request, queryset):
        for user in queryset:
            services.delete_user(user=user, requested_by=request.user)

    @admin.display(description=_("2FA (Google Auth)"))
    def two_factor_badge(self, obj):
        if obj is None:
            return "—"
        is_enabled = accounts_selectors.is_two_factor_enabled(obj)
        if is_enabled:
            return format_html(
                '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">🛡️ {}</span>',
                _("Aktif (Terenkripsi)"),
            )
        return format_html(
            '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400">⚪ {}</span>',
            _("Belum Aktif"),
        )

    @admin.display(description=_("Effective access"))
    def effective_access_summary(self, obj):
        if obj is None:
            return "—"

        groups = ", ".join(g.name for g in accounts_selectors.list_user_groups(obj))
        permissions = ", ".join(sorted(accounts_selectors.get_user_permissions(obj)))

        grant_bits = []
        for grant in access_selectors.user_feature_grants(obj):
            grantee = str(grant.group) if grant.group is not None else _("user")
            grant_bits.append(f"{grant.feature.slug} · {grant.effect} · {grantee}")
        grants = "<br>".join(grant_bits)

        features = ", ".join(sorted(access_selectors.effective_features(obj)))

        return format_html(
            "<strong>{}</strong>: {}<br>"
            "<strong>{}</strong>: {}<br>"
            "<strong>{}</strong>: {}<br>"
            "<strong>{}</strong>: {}",
            _("Groups"),
            groups or "—",
            _("Permissions"),
            permissions or "—",
            _("Menu grants"),
            grants or "—",
            _("Features"),
            features or "—",
        )
