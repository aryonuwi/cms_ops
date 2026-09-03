"""Unfold-styled admin for the accounts module."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.access import selectors as access_selectors
from apps.common.admin import BaseModelAdmin

from . import selectors as accounts_selectors
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin, BaseModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ("email", "first_name", "last_name", "is_staff", "status")
    list_filter = ("status", "is_staff", "is_superuser", "groups")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    filter_horizontal = ("groups", "user_permissions")

    # `is_active` is derived from `status` in `User.save()`, so the enum field
    # is what gets shown and edited here.
    readonly_fields = ("effective_access_summary",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "status",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
        (_("Effective access"), {"fields": ("effective_access_summary",)}),
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

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        # Only a superuser may hand out staff/superuser rights, manage groups
        # and permissions, or change an account's status. `is_staff` was a gap
        # before: a non-superuser could promote themselves or others.
        if not request.user.is_superuser:
            readonly += ["is_staff", "is_superuser", "user_permissions", "groups", "status"]
        return readonly

    @admin.display(description=_("Effective access"))
    def effective_access_summary(self, obj):
        if obj is None:
            return "—"

        # Cross-module reads go through selectors only (R3) - accounts for
        # groups/permissions, access for grants and feature reach.
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
