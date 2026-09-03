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
        # Bookkeeping columns are set by the ORM; never let them be typed in.
        for name in ("id", "created_at", "updated_at"):
            if obj is not None and hasattr(obj, name) and name not in readonly:
                readonly.append(name)
        return readonly


class BaseTabularInline(TabularInline):
    pass


class BaseStackedInline(StackedInline):
    pass
