from django.apps import AppConfig


class AccessConfig(AppConfig):
    """Who may reach what: the feature catalog and its grants."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.access"
    verbose_name = "Access"

    def ready(self) -> None:
        # Event subscriptions are wired here - importing them earlier would
        # touch the app registry before it is populated.
        from . import handlers  # noqa: F401
