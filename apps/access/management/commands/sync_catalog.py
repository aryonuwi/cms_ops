"""Management command: scan and install the Module → Feature → Action catalog."""

from django.core.management.base import BaseCommand

from apps.access import services


class Command(BaseCommand):
    help = "Upsert the access catalog (modules, features, actions) from code"

    def handle(self, *args, **options):
        result = services.sync_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                "catalog: "
                f"modules {result.modules_created} created / {result.modules_updated} updated, "
                f"features {result.features_created} created / {result.features_updated} updated, "
                f"actions {result.actions_created} created / {result.actions_updated} updated"
            )
        )
