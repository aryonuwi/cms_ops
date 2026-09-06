"""Management command: buat akun staff non-superuser untuk menguji hak akses.

`seed_admin` selalu bypass `apps.access.FeatureGrant` (superuser bypass -
ADR-012), jadi tidak bisa dipakai memverifikasi menu mana yang benar-benar
terlihat/tertutup untuk grup atau grant personal tertentu. Akun ini mengisi
celah itu: bisa login ke admin, tapi tunduk sepenuhnya pada evaluasi
`apps.access.selectors.user_can_access` seperti operator biasa.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import selectors, services


class Command(BaseCommand):
    help = "Buat akun test non-admin dari DJANGO_SEED_DUMMY_EMAIL/PASSWORD"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Izinkan seeding saat DEBUG=False. Wajib di server, supaya "
                "kredensial contoh dari .env.example tidak pernah ikut "
                "ter-seed ke production tanpa disengaja."
            ),
        )

    def handle(self, *args, **options):
        email = settings.SEED_DUMMY_EMAIL
        password = settings.SEED_DUMMY_PASSWORD

        if not email or not password:
            raise CommandError(
                "DJANGO_SEED_DUMMY_EMAIL dan DJANGO_SEED_DUMMY_PASSWORD belum "
                "diisi di .env. Salin nilainya dari .env.example."
            )

        # Kredensial default di .env.example diketahui publik lewat repo. Di
        # production seeding harus jadi tindakan sadar, bukan efek samping
        # dari menyalin .env.example apa adanya.
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "DEBUG=False: seeding akun dummy butuh --force."
            )

        # Idempotent seperti `seed_admin`: setup boleh dijalankan ulang tanpa
        # menimpa password atau grant akses yang sudah diberikan manual lewat
        # admin (Access -> Feature grants).
        existing = selectors.get_user_by_email(email)
        if existing is not None:
            self.stdout.write(
                self.style.WARNING(f"dummy: {existing.email} sudah ada, dilewati")
            )
            return

        user = services.register_user(
            email=email,
            password=password,
            is_staff=True,
            is_superuser=False,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"dummy: {user.email} dibuat - belum ada akses menu, "
                "beri lewat admin (Access -> Feature grants)"
            )
        )
