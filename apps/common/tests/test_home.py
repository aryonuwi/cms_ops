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

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_readiness_reports_cache_ok_when_reachable(self):
        response = self.client.get(reverse("common:readiness"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"]["cache:default"], "ok")

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                # Port tidak dipakai siapa pun di loopback - selalu connection
                # refused, tanpa bergantung pada Redis sungguhan hidup/mati.
                "LOCATION": "redis://127.0.0.1:1/0",
            }
        }
    )
    def test_readiness_reports_cache_error_without_flipping_overall_health(self):
        # Cache itu opsional (ADR-015): Redis down tidak boleh membuat probe
        # readiness gagal dan menjatuhkan traffic yang sebenarnya masih bisa
        # dilayani lewat database.
        response = self.client.get(reverse("common:readiness"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertTrue(response.json()["checks"]["cache:default"].startswith("error:"))
