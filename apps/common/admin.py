"""Admin scaffolding shared by every feature module.

Feature modules subclass `BaseModelAdmin` instead of `django.contrib.admin`'s
`ModelAdmin`, which is what gives them Unfold's styling and widgets.
"""

from unfold.admin import ModelAdmin, StackedInline, TabularInline

__all__ = ["BaseModelAdmin", "BaseStackedInline", "BaseTabularInline"]


class BaseModelAdmin(ModelAdmin):
    """Unfold-styled ModelAdmin with safe project-wide defaults."""

    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_fullwidth = False

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        # Bookkeeping and audit columns are managed by system/ORM; never let them be typed in.
        audit_fields = (
            "id",
            "created_at",
            "updated_at",
            "created_by_id",
            "updated_by_id",
            "is_deleted",
            "deleted_at",
            "deleted_by_id",
        )
        for name in audit_fields:
            if obj is not None and hasattr(obj, name) and name not in readonly:
                readonly.append(name)
        return readonly

    def save_model(self, request, obj, form, change):
        user_id = getattr(request.user, "pk", None)
        if not change and hasattr(obj, "created_by_id") and not getattr(obj, "created_by_id", None) and user_id:
            obj.created_by_id = user_id
        if hasattr(obj, "updated_by_id") and user_id:
            obj.updated_by_id = user_id
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        user_id = getattr(request.user, "pk", None)
        if hasattr(obj, "delete"):
            obj.delete(deleted_by_id=user_id)
        else:
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        user_id = getattr(request.user, "pk", None)
        if hasattr(queryset, "delete"):
            queryset.delete(deleted_by_id=user_id)
        else:
            super().delete_queryset(request, queryset)


class BaseTabularInline(TabularInline):
    pass


class BaseStackedInline(StackedInline):
    pass
