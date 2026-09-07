"""Unfold-styled admin for the access module."""

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils.html import format_html
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


class CatalogReadOnlyAdmin(SuperuserOnlyAdmin):
    """Guards catalog items (Module, Feature, Action) from manual UI creation.

    Slugs and labels are auto-generated from module code declarations (navigation.py
    and actions.py). They are strictly synced via services.sync_catalog.
    """

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    actions = ["sync_catalog_action"]

    @admin.action(description=_("🔄 Sinkronisasi Katalog dari File Modul (actions.py & navigation.py)"))
    def sync_catalog_action(self, request, queryset=None):
        res = services.sync_catalog()
        self.message_user(
            request,
            _(
                f"Katalog berhasil disinkronisasi: {res.modules_created} modul baru, "
                f"{res.features_created} fitur baru, {res.actions_created} aksi baru."
            ),
            messages.SUCCESS,
        )


@admin.register(Group)
class GroupAdmin(SuperuserOnlyAdmin, BaseGroupAdmin, BaseModelAdmin):
    list_display = ("name", "members_count", "grants_count")
    readonly_fields = ("members_summary", "grants_summary")

    fieldsets = (
        (
            _("Informasi Grup (Role)"),
            {
                "fields": ("name",),
                "description": _(
                    "Grup merepresentasikan peran/role tim (contoh: Staff Gudang, Supervisor, Finance)."
                ),
            },
        ),
        (
            _("Anggota dalam Grup ini"),
            {
                "fields": ("members_summary",),
                "description": _(
                    "Daftar pengguna yang saat ini menjadi anggota grup ini. Untuk menambah/mengurangi anggota, buka menu Users."
                ),
            },
        ),
        (
            _("Hak Akses (Feature Grants) Grup"),
            {
                "fields": ("grants_summary",),
                "description": _(
                    "Hak akses fitur dan aksi yang saat ini diberikan kepada grup ini."
                ),
            },
        ),
    )

    @admin.display(description=_("Jumlah Anggota"))
    def members_count(self, obj: Group) -> int:
        return obj.user_set.count()

    @admin.display(description=_("Jumlah Grant"))
    def grants_count(self, obj: Group) -> int:
        return obj.feature_grants.count()

    @admin.display(description=_("Anggota"))
    def members_summary(self, obj: Group):
        if not obj or not obj.pk:
            return "—"
        users = list(obj.user_set.values_list("email", flat=True)[:30])
        if not users:
            return format_html(
                '<span class="text-slate-400"><em>{}</em></span>',
                _("Belum ada anggota di grup ini."),
            )
        bits = [format_html('<li class="py-0.5">• {}</li>', u) for u in users]
        return format_html('<ul class="text-xs space-y-1">{}</ul>', format_html("{}", "".join(str(b) for b in bits)))

    @admin.display(description=_("Hak Akses Diberikan"))
    def grants_summary(self, obj: Group):
        if not obj or not obj.pk:
            return "—"
        grants = obj.feature_grants.select_related("feature", "action").all()
        if not grants:
            return format_html(
                '<span class="text-slate-400"><em>{}</em></span>',
                _("Belum ada hak akses untuk grup ini. Buat di menu Feature Grants."),
            )
        bits = []
        for g in grants:
            action_label = f" ➔ Aksi: {g.action.slug}" if g.action else f" ➔ {_('Seluruh Fitur')}"
            color = "green" if g.effect == FeatureGrant.Effect.ALLOW else "red"
            bits.append(
                format_html(
                    '<li class="py-1 text-xs"><strong>{}</strong> ({}){} '
                    '<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-{}-100 text-{}-800">{}</span></li>',
                    g.feature.label,
                    g.feature.slug,
                    action_label,
                    color,
                    color,
                    g.effect.upper(),
                )
            )
        return format_html('<ul class="space-y-1">{}</ul>', format_html("{}", "".join(str(b) for b in bits)))


@admin.register(Feature)
class FeatureAdmin(CatalogReadOnlyAdmin, BaseModelAdmin):
    list_display = ("label", "slug", "module", "required_permission", "is_active")
    list_filter = ("module", "is_active")
    search_fields = ("slug", "label", "description")
    readonly_fields = ("slug", "label", "module", "description", "required_permission")


@admin.register(Module)
class ModuleAdmin(CatalogReadOnlyAdmin, BaseModelAdmin):
    list_display = ("label", "slug", "package", "is_active", "order")
    list_filter = ("is_active",)
    search_fields = ("slug", "label", "package")
    readonly_fields = ("slug", "label", "package", "description", "order")


@admin.register(Action)
class ActionAdmin(CatalogReadOnlyAdmin, BaseModelAdmin):
    list_display = ("label", "slug", "code", "feature", "category", "is_active")
    list_filter = ("category", "is_active", "feature__module")
    list_select_related = ("feature",)
    search_fields = ("slug", "code", "label", "feature__slug")
    readonly_fields = ("slug", "code", "label", "feature", "category", "required_permission")


class ActionSelectWidget(forms.Select):
    """Select widget that annotates each <option> with its feature_id for client-side filtering."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value:
            action_obj = getattr(value, "instance", None) or Action.objects.filter(pk=value).first()
            if action_obj:
                option["attrs"]["data-feature"] = str(action_obj.feature_id)
        return option


class FeatureGrantForm(forms.ModelForm):
    """Pick a grantee by name with dynamic action selection and friendly tooltips."""

    user = forms.ModelChoiceField(
        queryset=accounts_selectors.list_active_users(),
        required=False,
        label=_("Pengguna (Personal)"),
        help_text=_(
            "Pilih pengguna spesifik jika izin ini hanya ditujukan khusus untuk satu orang (Grantee Type: User)."
        ),
    )

    class Media:
        js = ("access/js/dynamic_actions.js",)

    class Meta:
        model = FeatureGrant
        fields = ("feature", "action", "grantee_type", "group", "org_unit", "effect")
        widgets = {
            "action": ActionSelectWidget(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Friendly labels and helpful tooltips
        self.fields["feature"].label = _("Modul / Fitur")
        self.fields["feature"].help_text = _(
            "Pilih fitur aplikasi yang ingin diatur hak aksesnya (misal: Kelola Pengguna)."
        )

        self.fields["action"].label = _("Aksi Spesifik")
        self.fields["action"].empty_label = _("— Semua Action (Akses Penuh Fitur) —")
        self.fields["action"].help_text = _(
            "Pilih aksi spesifik (misal: Lihat, Buat, Edit, Hapus). KOSONGKAN jika ingin memberikan hak untuk SEMUA aksi dalam fitur ini."
        )

        self.fields["grantee_type"].label = _("Tipe Penerima Izin (Grantee Type)")
        self.fields["grantee_type"].help_text = _(
            "Tentukan target penerima izin: Group (Role Tim), User (Pengguna Pribadi), atau Org Unit (Divisi Organisasi)."
        )

        self.fields["group"].label = _("Grup / Role")
        self.fields["group"].help_text = _(
            "Pilih grup role penerima hak akses ini (diperlukan jika Grantee Type = Group)."
        )

        self.fields["org_unit"].label = _("Unit Organisasi / Divisi")
        self.fields["org_unit"].help_text = _(
            "Pilih unit organisasi (diperlukan jika Grantee Type = Org unit)."
        )

        self.fields["effect"].label = _("Efek Keputusan")
        self.fields["effect"].help_text = _(
            "Allow = Berikan izin akses; Deny = Blokir hak akses secara tegas (Deny menang atas Allow)."
        )

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
            raise ValidationError(
                _("Aksi yang dipilih tidak cocok atau bukan bagian dari fitur tersebut.")
            )

        if grantee_type == FeatureGrant.GranteeType.GROUP:
            if group is None:
                raise ValidationError(_("Pemberian izin tipe Grup wajib memilih satu Grup."))
        elif grantee_type == FeatureGrant.GranteeType.USER:
            if user is None:
                raise ValidationError(_("Pemberian izin tipe Pengguna wajib memilih satu Pengguna."))
        elif grantee_type == FeatureGrant.GranteeType.ORG_UNIT:
            if org_unit is None:
                raise ValidationError(_("Pemberian izin tipe Unit Organisasi wajib memilih satu Divisi."))
        else:
            raise ValidationError(_("Silakan pilih tipe penerima izin."))

        if len([g for g in (group, user, org_unit) if g is not None]) > 1:
            raise ValidationError(_("Pilih tepat satu penerima izin (Grup, User, atau Org Unit)."))
        return cleaned

    def save(self, commit: bool = True):
        user = self.cleaned_data.get("user")
        self.instance.user_id = user.pk if user is not None else None
        return super().save(commit=commit)


@admin.register(FeatureGrant)
class FeatureGrantAdmin(SuperuserOnlyAdmin, BaseModelAdmin):
    form = FeatureGrantForm
    list_display = ("feature", "action_display", "grantee", "effect_badge")
    list_filter = ("effect", "grantee_type", "feature")
    list_select_related = ("feature", "action", "group", "org_unit")
    search_fields = ("feature__slug", "action__slug", "group__name")

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["instructions_card"] = True
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description=_("Aksi"))
    def action_display(self, obj: FeatureGrant) -> str:
        if obj.action:
            return format_html('<code class="text-xs">{}</code>', obj.action.label or obj.action.code)
        return format_html(
            '<span class="px-2 py-0.5 rounded text-[11px] font-medium bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">★ {}</span>',
            _("Seluruh Fitur"),
        )

    @admin.display(description=_("Efek"))
    def effect_badge(self, obj: FeatureGrant) -> str:
        if obj.effect == FeatureGrant.Effect.ALLOW:
            return format_html(
                '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">✓ ALLOW</span>'
            )
        return format_html(
            '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">✕ DENY</span>'
        )

    @admin.display(description=_("Penerima Izin (Grantee)"))
    def grantee(self, obj: FeatureGrant) -> str:
        if obj.grantee_type == FeatureGrant.GranteeType.GROUP:
            return format_html('👥 <strong>{}</strong> (Grup)', obj.group)
        if obj.grantee_type == FeatureGrant.GranteeType.ORG_UNIT:
            return format_html('🏢 <strong>{}</strong> (Divisi)', obj.org_unit)
        user = accounts_selectors.get_user_by_id(obj.user_id)
        return format_html('👤 <strong>{}</strong> (User)', user or obj.user_id)

    def save_model(self, request, obj, form, change):
        # R5: through services.py
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
    user = forms.ModelChoiceField(
        queryset=accounts_selectors.list_active_users(),
        required=False,
        label=_("Pengguna"),
        help_text=_("Pilih akun pengguna yang ditugaskan ke dalam unit organisasi ini."),
    )

    class Meta:
        model = OrgUnitMembership
        fields = ("org_unit",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["org_unit"].label = _("Unit Organisasi / Divisi")
        if self.instance is not None and self.instance.user_id:
            self.fields["user"].initial = accounts_selectors.get_user_by_id(
                self.instance.user_id
            )
        if self.instance is not None and self.instance.pk:
            self.fields["org_unit"].disabled = True
            self.fields["user"].disabled = True

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get("user"):
            raise ValidationError(_("Silakan pilih pengguna."))
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

    @admin.display(description=_("Anggota"))
    def member(self, obj: OrgUnitMembership) -> str:
        user = accounts_selectors.get_user_by_id(obj.user_id)
        return str(user) if user is not None else str(obj.user_id)

    def save_model(self, request, obj, form, change):
        membership = services.add_org_member(org_unit=obj.org_unit, user_id=obj.user_id)
        obj.pk = membership.pk

    def delete_model(self, request, obj):
        services.remove_org_member(membership=obj)

    def delete_queryset(self, request, queryset):
        for membership in queryset:
            services.remove_org_member(membership=membership)
