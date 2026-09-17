"""Deprecated alias for ``sync_catalog``.

Kept so operator muscle memory keeps working; the catalog now spans modules,
features and actions, so new runs should call ``sync_catalog``.
"""

from django.core.management.base import BaseCommand

from apps.access import services


class Command(BaseCommand):
    help = "Deprecated alias for sync_catalog (scans modules, features and actions)"

    def handle(self, *args, **options):
        result = services.sync_catalog()
        self.stdout.write(
            self.style.WARNING("sync_features is deprecated; use sync_catalog instead.")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"features: {result.features_created} created, "
                f"{result.features_updated} updated"
            )
        )
