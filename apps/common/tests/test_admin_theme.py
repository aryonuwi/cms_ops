"""Tema admin dipasang lewat UNFOLD["STYLES"].

Wiring ini gampang putus tanpa suara - stylesheet-nya hilang, admin tetap
jalan, dan tidak ada yang sadar sampai ada yang membuka halamannya.
"""

from django.test import TestCase
from django.urls import reverse


class AdminThemeTests(TestCase):
    def test_login_page_loads_shared_theme(self):
        response = self.client.get(reverse("admin:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "common/admin.css")

    def test_theme_stylesheet_is_collectable(self):
        # `static()` hanya menghasilkan URL; kalau berkasnya tidak ada,
        # collectstatic di production yang gagal - bukan test ini.
        from django.contrib.staticfiles import finders

        self.assertIsNotNone(finders.find("common/admin.css"))
        self.assertIsNotNone(finders.find("common/home.css"))
