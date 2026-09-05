"""Unfold-styled admin for the access module."""

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.accounts import selectors as accounts_selectors
from apps.common.admin import BaseModelAdmin

from . import services
from .models import Action, Feature, FeatureGrant, Module

# django.contrib.auth registers Group with the stock ModelAdmin; re-register it
# here so grouping lives with the rest of access control and renders
# consistently under Unfold.
admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, BaseModelAdmin):
    pass


@admin.register(Feature)
class FeatureAdmin(BaseModelAdmin):
    list_display = ("slug", "label", "module", "required_permission", "is_active")
    list_filter = ("module", "is_active")
    search_fields = ("slug", "label", "description")


@admin.register(Module)
class ModuleAdmin(BaseModelAdmin):
    list_display = ("slug", "label", "package", "is_active", "order")
    list_filter = ("is_active",)
    search_fields = ("slug", "label", "package")


@admin.register(Action)
class ActionAdmin(BaseModelAdmin):
    list_display = ("slug", "code", "feature", "category", "required_permission", "is_active")
    list_filter = ("category", "is_active", "feature__module")
    list_select_related = ("feature",)
    search_fields = ("slug", "code", "label", "feature__slug")


class FeatureGrantForm(forms.ModelForm):
    """Pick a grantee by name instead of typing raw identifiers.

    Users are offered through the accounts read API (R3 - never its models);
    the chosen user is stored as a plain id on the grant (R4).
    """

    user = forms.ModelChoiceField(
        queryset=accounts_selectors.list_active_users(),
        required=False,
        label=_("user"),
        help_text=_("Pick a user for a personal grant."),
    )

    class Meta:
        model = FeatureGrant
        fields = ("feature", "grantee_type", "group", "effect")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None and self.instance.user_id:
            self.fields["user"].initial = accounts_selectors.get_user_by_id(
                self.instance.user_id
            )

    def clean(self):
        cleaned = super().clean()
        grantee_type = cleaned.get("grantee_type")
        group = cleaned.get("group")
        user = cleaned.get("user")

        if grantee_type == FeatureGrant.GranteeType.GROUP and group is None:
            raise ValidationError(_("A group grant needs a group."))
        if grantee_type == FeatureGrant.GranteeType.USER and user is None:
            raise ValidationError(_("A personal grant needs a user."))
        if group is not None and user is not None:
            raise ValidationError(_("Pick a group or a user, not both."))
        return cleaned

    def save(self, commit: bool = True):
        # Map the friendly `user` picker onto the raw cross-module id (R4)
        # before the admin hands the instance to save_model.
        user = self.cleaned_data.get("user")
        self.instance.user_id = user.pk if user is not None else None
        return super().save(commit=commit)


@admin.register(FeatureGrant)
class FeatureGrantAdmin(BaseModelAdmin):
    form = FeatureGrantForm
    list_display = ("feature", "grantee", "effect")
    list_filter = ("effect", "grantee_type", "feature")
    list_select_related = ("feature", "group")
    search_fields = ("feature__slug", "group__name")

    @admin.display(description=_("grantee"))
    def grantee(self, obj: FeatureGrant) -> str:
        if obj.grantee_type == FeatureGrant.GranteeType.GROUP:
            return str(obj.group) if obj.group is not None else "—"
        # Rendered through the accounts read API (R3) - no model import.
        user = accounts_selectors.get_user_by_id(obj.user_id)
        return str(user) if user is not None else str(obj.user_id)

    def save_model(self, request, obj, form, change):
        # R5: the write goes through the service so upsert semantics and the
        # access.feature_granted event behave identically for admin and code.
        grant = services.grant_feature(
            feature=obj.feature,
            grantee_type=obj.grantee_type,
            group=obj.group,
            user_id=obj.user_id,
            effect=obj.effect,
        )
        # Keep the admin (messages, redirect, log entry) pointing at the row
        # the service actually persisted.
        obj.pk = grant.pk

    def delete_model(self, request, obj):
        services.revoke_feature(grant=obj)

    def delete_queryset(self, request, queryset):
        for grant in queryset:
            services.revoke_feature(grant=grant)
