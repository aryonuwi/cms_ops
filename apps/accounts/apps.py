from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Identity and access. Owns the project's user model."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        # Event subscriptions are wired here - importing them earlier would
        # touch the app registry before it is populated.
        from . import handlers  # noqa: F401
