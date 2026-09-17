"""Unfold-styled admin for the accounts module."""

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils.timezone import localtime
from django.utils.translation import gettext_lazy as _
from unfold.forms import AdminPasswordChangeForm, UserCreationForm

from apps.access import selectors as access_selectors
from apps.common.admin import BaseModelAdmin

from . import selectors as accounts_selectors
from . import services
from .forms import CustomUserChangeForm
from .models import User, UserActivity


@admin.register(User)
class UserAdmin(BaseUserAdmin, BaseModelAdmin):
    change_form_template = "admin/accounts/user/change_form.html"
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
        "user_activity_summary",
    )

    fieldsets = (
        (
            _("Kredensial Akun"),
            {
                "classes": ("tab",),
                "fields": ("email", "new_password", "confirm_new_password"),
                "description": _(
                    "Alamat email login dan satu form Password Baru. Biarkan kosong jika password tidak ingin diubah."
                ),
            },
        ),
        (
            _("Informasi Pengguna"),
            {
                "classes": ("tab",),
                "fields": ("first_name", "last_name"),
                "description": _("Nama depan dan belakang pengguna."),
            },
        ),
        (
            _("Hak Akses & Status"),
            {
                "classes": ("tab",),
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
                "classes": ("tab",),
                "fields": ("two_factor_badge",),
                "description": _(
                    "Status Autentikasi Dua Langkah. Jika aktif, token disimpan dalam database dengan enkripsi simetris dinamis."
                ),
            },
        ),
        (
            _("Jejak Audit & Tanggal"),
            {
                "classes": ("tab",),
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
        (
            _("Ringkasan Akses Efektif"),
            {"classes": ("tab",), "fields": ("effective_access_summary",)},
        ),
        (
            _("Aktivitas User"),
            {"classes": ("tab",), "fields": ("user_activity_summary",)},
        ),
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

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/reset-2fa/",
                self.admin_site.admin_view(self.reset_two_factor_view),
                name="accounts_user_reset_two_factor",
            ),
            path(
                "<path:object_id>/send-password-reset/",
                self.admin_site.admin_view(self.send_password_reset_view),
                name="accounts_user_send_password_reset",
            ),
        ]
        return custom_urls + super().get_urls()

    def changeform_view(
        self,
        request: HttpRequest,
        object_id=None,
        form_url="",
        extra_context=None,
    ):
        extra_context = dict(extra_context or {})
        if object_id and request.user.is_superuser:
            extra_context["two_factor_reset_url"] = reverse(
                "admin:accounts_user_reset_two_factor",
                args=[object_id],
            )
            extra_context["password_reset_url"] = reverse(
                "admin:accounts_user_send_password_reset",
                args=[object_id],
            )
        return super().changeform_view(request, object_id, form_url, extra_context)

    def reset_two_factor_view(self, request: HttpRequest, object_id: str):
        """Confirm and reset one user's TOTP enrollment from the admin detail page."""
        if not request.user.is_superuser:
            raise PermissionDenied

        user = accounts_selectors.get_user_by_id(object_id)
        if user is None:
            raise Http404

        if request.method == "POST":
            services.disable_two_factor(user=user, requested_by=request.user)
            self.message_user(
                request,
                _(f"2FA untuk {user.email} berhasil di-reset."),
                messages.SUCCESS,
            )
            return redirect("admin:accounts_user_change", user.pk)

        context = {
            **self.admin_site.each_context(request),
            "title": _("Reset 2FA"),
            "user_obj": user,
            "cancel_url": reverse("admin:accounts_user_change", args=[user.pk]),
        }
        return TemplateResponse(
            request,
            "admin/accounts/user/reset_two_factor.html",
            context,
        )

    def send_password_reset_view(self, request: HttpRequest, object_id: str):
        """Confirm and email a one-time password reset link to one user."""
        if not request.user.is_superuser:
            raise PermissionDenied

        user = accounts_selectors.get_user_by_id(object_id)
        if user is None:
            raise Http404

        if request.method == "POST":
            services.send_password_reset_link(
                user=user,
                site_url=request.build_absolute_uri("/"),
                requested_by_id=request.user.pk,
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            self.message_user(
                request,
                _(f"Link reset password untuk {user.email} berhasil dikirim."),
                messages.SUCCESS,
            )
            return redirect("admin:accounts_user_change", user.pk)

        context = {
            **self.admin_site.each_context(request),
            "title": _("Kirim Link Reset Password"),
            "user_obj": user,
            "cancel_url": reverse("admin:accounts_user_change", args=[user.pk]),
        }
        return TemplateResponse(
            request,
            "admin/accounts/user/send_password_reset.html",
            context,
        )

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
                if status is not None and status != form.initial.get("status"):
                    # ModelForm has already copied the new value onto obj;
                    # restore the persisted value so the service can apply the
                    # transition and publish its event exactly once.
                    obj.status = form.initial.get("status")
                    if status == User.Status.ACTIVE:
                        services.activate_user(user=obj, requested_by_id=request.user.pk)
                    elif status == User.Status.SUSPENDED:
                        services.suspend_user(user=obj, requested_by_id=request.user.pk)
                    else:
                        services.deactivate_user(user=obj, requested_by_id=request.user.pk)
                is_staff = form.cleaned_data.get("is_staff")
                if is_staff is not None and is_staff != form.initial.get("is_staff"):
                    obj.is_staff = is_staff
                    obj.save(update_fields=["is_staff"])
                is_superuser = form.cleaned_data.get("is_superuser")
                if is_superuser is not None and is_superuser != form.initial.get("is_superuser"):
                    obj.is_superuser = is_superuser
                    obj.save(update_fields=["is_superuser"])
                privileged_changes = [
                    field
                    for field in ("is_staff", "is_superuser")
                    if field in form.changed_data
                ]
                if privileged_changes:
                    services.record_activity(
                        user_id=obj.pk,
                        actor_id=request.user.pk,
                        action=UserActivity.Action.USER_UPDATED,
                        description="Hak akses user diperbarui.",
                        details={"fields": privileged_changes},
                    )
        else:
            if not getattr(obj, "created_by_id", None):
                obj.created_by_id = request.user.pk
            obj.updated_by_id = request.user.pk
            super().save_model(request, obj, form, change)
            services.record_activity(
                user_id=obj.pk,
                actor_id=request.user.pk,
                action=UserActivity.Action.USER_CREATED,
                description="Akun user dibuat melalui admin.",
            )

    def save_related(self, request, form, formsets, change):
        """Record group and personal-permission changes after Django saves them."""
        user = form.instance
        before_groups = {
            group.pk: group.name for group in user.groups.all()
        }
        before_permissions = {
            permission.pk: permission.codename
            for permission in user.user_permissions.all()
        }

        super().save_related(request, form, formsets, change)

        after_groups = {group.pk: group.name for group in user.groups.all()}
        after_permissions = {
            permission.pk: permission.codename
            for permission in user.user_permissions.all()
        }
        for group_id in after_groups.keys() - before_groups.keys():
            services.record_activity(
                user_id=user.pk,
                actor_id=request.user.pk,
                action=UserActivity.Action.GROUP_ASSIGNED,
                description=f"Group {after_groups[group_id]} ditambahkan.",
                details={"group_id": str(group_id)},
            )
        for group_id in before_groups.keys() - after_groups.keys():
            services.record_activity(
                user_id=user.pk,
                actor_id=request.user.pk,
                action=UserActivity.Action.GROUP_UNASSIGNED,
                description=f"Group {before_groups[group_id]} dihapus.",
                details={"group_id": str(group_id)},
            )
        for permission_id in after_permissions.keys() - before_permissions.keys():
            services.record_activity(
                user_id=user.pk,
                actor_id=request.user.pk,
                action=UserActivity.Action.PERMISSION_GRANTED,
                description=f"Permission {after_permissions[permission_id]} diberikan.",
                details={"permission_id": permission_id},
            )
        for permission_id in before_permissions.keys() - after_permissions.keys():
            services.record_activity(
                user_id=user.pk,
                actor_id=request.user.pk,
                action=UserActivity.Action.PERMISSION_REVOKED,
                description=f"Permission {before_permissions[permission_id]} dicabut.",
                details={"permission_id": permission_id},
            )

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

    @admin.display(description=_("Aktivitas User"))
    def user_activity_summary(self, obj):
        if obj is None:
            return "—"

        activities = list(
            accounts_selectors.list_user_activities(user_id=obj.pk, limit=25)
        )
        if not activities:
            return format_html(
                '<p class="text-subtle">{}</p>',
                _("Belum ada aktivitas yang tercatat."),
            )

        actor_ids = {activity.actor_id for activity in activities if activity.actor_id}
        actors = accounts_selectors.list_users_by_ids(user_ids=actor_ids)
        actor_labels = {str(actor.pk): actor.email for actor in actors}
        rows = format_html_join(
            "",
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>",
            (
                (
                    localtime(activity.created_at).strftime("%d/%m/%Y %H:%M"),
                    activity.get_action_display(),
                    activity.description or "—",
                    actor_labels.get(str(activity.actor_id), _("Sistem")),
                )
                for activity in activities
            ),
        )
        return format_html(
            '<div class="overflow-x-auto"><table class="w-full text-sm">'
            '<thead><tr class="text-left text-subtle">'
            '<th class="px-3 py-2">{}</th><th class="px-3 py-2">{}</th>'
            '<th class="px-3 py-2">{}</th><th class="px-3 py-2">{}</th>'
            "</tr></thead><tbody>{}</tbody></table></div>",
            _("Waktu"),
            _("Aktivitas"),
            _("Keterangan"),
            _("Dilakukan oleh"),
            rows,
        )
