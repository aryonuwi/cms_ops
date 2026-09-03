"""Management command: refresh the access Feature catalog from code."""

from django.core.management.base import BaseCommand

from apps.access import services


class Command(BaseCommand):
    help = "Upsert the access Feature catalog from each module's navigation.py"

    def handle(self, *args, **options):
        created, updated = services.sync_features()
        self.stdout.write(
            self.style.SUCCESS(f"features: {created} created, {updated} updated")
        )
