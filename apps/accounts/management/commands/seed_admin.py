"""Management command: buat akun admin pertama saat setup awal.

Menggantikan `createsuperuser` yang interaktif untuk alur setup yang harus
bisa dijalankan tanpa prompt (mesin baru, CI, container). Kredensialnya dibaca
dari environment (R2) - lihat `DJANGO_SEED_ADMIN_*` di `.env.example`.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import selectors, services


class Command(BaseCommand):
    help = "Buat akun admin pertama dari DJANGO_SEED_ADMIN_EMAIL/PASSWORD"

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
        email = settings.SEED_ADMIN_EMAIL
        password = settings.SEED_ADMIN_PASSWORD

        if not email or not password:
            raise CommandError(
                "DJANGO_SEED_ADMIN_EMAIL dan DJANGO_SEED_ADMIN_PASSWORD belum "
                "diisi di .env. Salin nilainya dari .env.example, atau pakai "
                "`manage.py createsuperuser` untuk input interaktif."
            )

        # Kredensial default di .env.example diketahui publik lewat repo. Di
        # production seeding harus jadi tindakan sadar, bukan efek samping
        # dari menyalin .env.example apa adanya.
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "DEBUG=False: seeding admin butuh --force. Di server, "
                "`manage.py createsuperuser` lebih tepat - kredensialnya tidak "
                "pernah singgah di file environment."
            )

        # Idempotent seperti `sync_features`: setup boleh dijalankan ulang
        # tanpa menimpa password admin yang sudah dipakai orang.
        existing = selectors.get_user_by_email(email)
        if existing is not None:
            self.stdout.write(
                self.style.WARNING(f"admin: {existing.email} sudah ada, dilewati")
            )
            return

        user = services.register_user(
            email=email,
            password=password,
            is_staff=True,
            is_superuser=True,
        )
        self.stdout.write(self.style.SUCCESS(f"admin: {user.email} dibuat"))
