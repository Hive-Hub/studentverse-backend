from __future__ import annotations

from django.urls import reverse
from rest_framework.test import APITestCase


class HealthEndpointTests(APITestCase):
    def test_health_endpoint_returns_ok(self):
        response = self.client.get(reverse("health-check"), HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message"], "Service is healthy")
        self.assertEqual(response.data["data"]["status"], "ok")
        self.assertEqual(response.data["data"]["database"]["connected"], True)


class VersionEndpointTests(APITestCase):
    def test_version_endpoint_returns_version(self):
        response = self.client.get(reverse("version"), HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message"], "API version retrieved successfully")
        self.assertEqual(response.data["data"]["version"], "0.1.0")
