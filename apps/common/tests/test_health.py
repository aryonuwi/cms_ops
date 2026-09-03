from django.test import TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    def test_liveness(self):
        response = self.client.get(reverse("common:liveness"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_checks_database(self):
        response = self.client.get(reverse("common:readiness"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"]["database:default"], "ok")
