from django.test import TestCase
from django.urls import reverse

from .models import User


class AuthTests(TestCase):
    def test_register_and_login_with_email(self):
        resp = self.client.post(reverse("accounts:register"), {
            "username": "sabbir", "first_name": "Sabbir", "last_name": "Ahmed", "email": "sab@example.com",
            "phone": "01712345678", "city": "Dhaka", "area": "Banani", "password1": "Str0ng!pass99",
            "password2": "Str0ng!pass99", "agree_terms": "on"})
        self.assertRedirects(resp, reverse("accounts:dashboard"))
        self.client.logout()
        self.assertTrue(self.client.login(username="sab@example.com", password="Str0ng!pass99"))

    def test_duplicate_email_and_bad_phone(self):
        User.objects.create_user("a", "dup@example.com", "pw12345678")
        resp = self.client.post(reverse("accounts:register"), {
            "username": "b", "first_name": "B", "last_name": "B", "email": "DUP@example.com", "phone": "123",
            "city": "Dhaka", "area": "x", "password1": "Str0ng!pass99", "password2": "Str0ng!pass99",
            "agree_terms": "on"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "already exists")
        self.assertContains(resp, "valid Bangladeshi mobile")

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(resp.status_code, 302)
