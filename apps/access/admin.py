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
from .models import Action, Feature, FeatureGrant, Module, OrgUnit, OrgUnitMembership

# django.contrib.auth registers Group with the stock ModelAdmin; re-register it
# here so grouping lives with the rest of access control and renders
# consistently under Unfold.
admin.site.unregister(Group)


class SuperuserOnlyAdmin:
    """Handing out access is as sensitive as handing out staff rights.

    Only superusers may open these admins - enforced at the URL level, not just
    the sidebar, so a stray model permission cannot be turned into self-grant.
    """

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Group)
class GroupAdmin(SuperuserOnlyAdmin, BaseGroupAdmin, BaseModelAdmin):
    pass


@admin.register(Feature)
class FeatureAdmin(SuperuserOnlyAdmin, BaseModelAdmin):
    list_display = ("slug", "label", "module", "required_permission", "is_active")
    list_filter = ("module", "is_active")
    search_fields = ("slug", "label", "description")


@admin.register(Module)
class ModuleAdmin(SuperuserOnlyAdmin, BaseModelAdmin):
    list_display = ("slug", "label", "package", "is_active", "order")
    list_filter = ("is_active",)
    search_fields = ("slug", "label", "package")


@admin.register(Action)
class ActionAdmin(SuperuserOnlyAdmin, BaseModelAdmin):
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
        fields = ("feature", "action", "grantee_type", "group", "org_unit", "effect")

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
        org_unit = cleaned.get("org_unit")
        feature = cleaned.get("feature")
        action = cleaned.get("action")

        if (
            action is not None
            and feature is not None
            and action.feature_id != feature.pk
        ):
            raise ValidationError(_("The action must belong to the chosen feature."))

        if grantee_type == FeatureGrant.GranteeType.GROUP:
            if group is None:
                raise ValidationError(_("A group grant needs a group."))
        elif grantee_type == FeatureGrant.GranteeType.USER:
            if user is None:
                raise ValidationError(_("A personal grant needs a user."))
        elif grantee_type == FeatureGrant.GranteeType.ORG_UNIT:
            if org_unit is None:
                raise ValidationError(_("An org-unit grant needs an org unit."))
        else:
            raise ValidationError(_("Pick a grantee type."))

        if len([g for g in (group, user, org_unit) if g is not None]) > 1:
            raise ValidationError(_("Pick one grantee, not several."))
        return cleaned

    def save(self, commit: bool = True):
        # Map the friendly `user` picker onto the raw cross-module id (R4)
        # before the admin hands the instance to save_model.
        user = self.cleaned_data.get("user")
        self.instance.user_id = user.pk if user is not None else None
        return super().save(commit=commit)


@admin.register(FeatureGrant)
class FeatureGrantAdmin(SuperuserOnlyAdmin, BaseModelAdmin):
    form = FeatureGrantForm
    list_display = ("feature", "action", "grantee", "effect")
    list_filter = ("effect", "grantee_type", "feature")
    list_select_related = ("feature", "action", "group", "org_unit")
    search_fields = ("feature__slug", "action__slug", "group__name")

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
            org_unit=obj.org_unit,
            action=obj.action,
            effect=obj.effect,
        )
        obj.pk = grant.pk

    def delete_model(self, request, obj):
        services.revoke_feature(grant=obj)

    def delete_queryset(self, request, queryset):
        for grant in queryset:
            services.revoke_feature(grant=grant)


@admin.register(OrgUnit)
class OrgUnitAdmin(SuperuserOnlyAdmin, BaseModelAdmin):
    list_display = ("name", "slug", "parent", "is_active", "order")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")


class OrgUnitMembershipForm(forms.ModelForm):
    """Pick a user by name; stored as a plain id on the membership (R4)."""

    user = forms.ModelChoiceField(
        queryset=accounts_selectors.list_active_users(),
        required=False,
        label=_("user"),
    )

    class Meta:
        model = OrgUnitMembership
        fields = ("org_unit",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None and self.instance.user_id:
            self.fields["user"].initial = accounts_selectors.get_user_by_id(
                self.instance.user_id
            )
        # Membership identity is immutable once created - move someone by
        # removing and re-adding. Disabling the fields on change prevents an
        # edit from silently spawning a second row.
        if self.instance is not None and self.instance.pk:
            self.fields["org_unit"].disabled = True
            self.fields["user"].disabled = True

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get("user"):
            raise ValidationError(_("Pick a user."))
        return cleaned

    def save(self, commit: bool = True):
        user = self.cleaned_data.get("user")
        if user is not None:
            self.instance.user_id = user.pk
        return super().save(commit=commit)


@admin.register(OrgUnitMembership)
class OrgUnitMembershipAdmin(SuperuserOnlyAdmin, BaseModelAdmin):
    form = OrgUnitMembershipForm
    list_display = ("org_unit", "member")
    list_filter = ("org_unit",)
    list_select_related = ("org_unit",)
    search_fields = ("org_unit__name", "org_unit__slug")

    @admin.display(description=_("member"))
    def member(self, obj: OrgUnitMembership) -> str:
        # Rendered through the accounts read API (R3) - no model import.
        user = accounts_selectors.get_user_by_id(obj.user_id)
        return str(user) if user is not None else str(obj.user_id)

    def save_model(self, request, obj, form, change):
        # R5: the write goes through the service so the event fires identically
        # for admin and code.
        membership = services.add_org_member(org_unit=obj.org_unit, user_id=obj.user_id)
        obj.pk = membership.pk

    def delete_model(self, request, obj):
        services.remove_org_member(membership=obj)

    def delete_queryset(self, request, queryset):
        for membership in queryset:
            services.remove_org_member(membership=membership)
