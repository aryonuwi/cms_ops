"""Halaman root harus terbuka tanpa login dan tidak membocorkan apa pun.

Sebelum ada halaman ini, `/` menjawab 404 - termasuk untuk link "return to
site" di halaman login admin.
"""

from django.test import TestCase, override_settings
from django.urls import reverse


class HomePageTests(TestCase):
    def test_is_public(self):
        response = self.client.get(reverse("common:home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "common/home.html")

    @override_settings(SITE_TITLE="Judul Uji")
    def test_uses_configured_site_title(self):
        response = self.client.get(reverse("common:home"))

        self.assertContains(response, "Judul Uji")

    def test_links_to_admin_without_hardcoding_the_path(self):
        response = self.client.get(reverse("common:home"))

        self.assertContains(response, reverse("admin:index"))

    def test_is_not_indexable(self):
        # Panel internal - jangan sampai muncul di mesin pencari.
        response = self.client.get(reverse("common:home"))

        self.assertContains(response, "noindex")

    def test_health_urls_are_unchanged_after_remount(self):
        # Probe orchestrator memakai path harfiah, bukan reverse().
        self.assertEqual(reverse("common:liveness"), "/health/live/")
        self.assertEqual(reverse("common:readiness"), "/health/ready/")
