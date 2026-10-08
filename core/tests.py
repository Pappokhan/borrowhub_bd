import io
import shutil
import tempfile
from datetime import timedelta

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import User
from bookings import services
from bookings.tests import make_world
from core.models import Notification, notify


def _jpeg(w=3000, h=2000):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 120, 90)).save(buf, "JPEG")
    return SimpleUploadedFile("big.jpg", buf.getvalue(), content_type="image/jpeg")


class OpsEndpointTests(TestCase):
    def test_healthz_robots_sitemap(self):
        r = self.client.get("/healthz/")
        self.assertEqual((r.status_code, r.json()["status"]), (200, "ok"))
        robots = self.client.get("/robots.txt").content.decode()
        self.assertIn("Disallow: /bookings/", robots)
        self.assertIn("sitemap.xml", robots)
        owner, renter, listing = make_world()
        sm = self.client.get("/sitemap.xml")
        self.assertEqual(sm.status_code, 200)
        self.assertIn(listing.slug, sm.content.decode())

    def test_security_headers(self):
        r = self.client.get("/")
        self.assertIn("Permissions-Policy", r.headers)


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user("dave", "dave@x.com", "RightPass!123")

    def test_lockout_after_failures(self):
        url = reverse("accounts:login")
        for _ in range(5):
            self.client.post(url, {"username": "dave", "password": "wrong"})
        r = self.client.post(url, {"username": "dave", "password": "RightPass!123"})
        self.assertContains(r, "Too many failed attempts")

    def test_success_resets_counter(self):
        url = reverse("accounts:login")
        for _ in range(3):
            self.client.post(url, {"username": "dave", "password": "wrong"})
        r = self.client.post(url, {"username": "dave@x.com", "password": "RightPass!123"})
        self.assertEqual(r.status_code, 302)

    def test_admin_login_is_throttled_too(self):
        User.objects.create_superuser("boss", "boss@x.com", "RightPass!123")
        url = reverse("admin:login")
        for _ in range(5):
            self.client.post(url, {"username": "boss", "password": "nope", "next": "/admin/"})
        r = self.client.post(url, {"username": "boss", "password": "RightPass!123", "next": "/admin/"})
        self.assertContains(r, "Too many failed attempts")


class ContactRateLimitTests(TestCase):
    def test_contact_form_limited(self):
        cache.clear()
        data = {"name": "A", "email": "a@x.com", "subject": "Hi", "message": "Hello there"}
        for _ in range(5):
            self.client.post(reverse("core:contact"), data)
        self.client.post(reverse("core:contact"), data)
        from core.models import ContactMessage
        self.assertEqual(ContactMessage.objects.count(), 5)


class UploadTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_images_are_downscaled(self):
        with override_settings(MEDIA_ROOT=self.tmp):
            owner, renter, listing = make_world()
            from listings.models import ListingImage
            img = ListingImage.objects.create(listing=listing, image=_jpeg())
            with Image.open(img.image.path) as im:
                self.assertLessEqual(max(im.size), 1600)

    def test_nid_photo_is_private_and_staff_only(self):
        from core.storage import PrivateMediaStorage
        priv = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, priv, True)
        with override_settings(PRIVATE_MEDIA_ROOT=priv, MEDIA_ROOT=self.tmp):
            user = User.objects.create_user("kyc", "kyc@x.com", "RightPass!123")
            storage = PrivateMediaStorage()
            name = storage.save("nid/test.jpg", _jpeg(200, 100))
            User.objects.filter(pk=user.pk).update(nid_photo=name)
            url = f"/private/{name}"
            self.assertEqual(self.client.get(url).status_code, 302)  # anonymous → login
            self.client.login(username="kyc", password="RightPass!123")
            self.assertEqual(self.client.get(url).status_code, 302)  # normal member → denied
            User.objects.create_superuser("boss", "boss@x.com", "RightPass!123")
            self.client.login(username="boss", password="RightPass!123")
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.client.get("/private/../../etc/passwd").status_code, 404)


class EmailNotificationTests(TestCase):
    @override_settings(EMAIL_NOTIFICATIONS=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_notify_sends_email_after_commit(self):
        owner, renter, listing = make_world()
        with self.captureOnCommitCallbacks(execute=True):
            notify(owner, "Hello owner", "/bookings/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Hello owner", mail.outbox[0].subject)
        self.assertEqual(Notification.objects.filter(user=owner).count(), 1)

    def test_no_email_by_default(self):
        owner, renter, listing = make_world()
        notify(owner, "Quiet")
        self.assertEqual(len(mail.outbox), 0)


class RegistrationRateLimitTests(TestCase):
    def test_register_limited(self):
        cache.clear()
        for i in range(11):
            r = self.client.post(reverse("accounts:register"), {"username": f"u{i}"})
        self.assertEqual(r.status_code, 429)
