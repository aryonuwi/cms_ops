from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Shared kernel: base models, the event bus, admin scaffolding.

    Every feature module may depend on `apps.common`. `apps.common` must
    never depend on a feature module - that keeps the dependency graph
    acyclic and each feature extractable.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    verbose_name = "Common"
