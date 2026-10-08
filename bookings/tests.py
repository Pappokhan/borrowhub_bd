from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from core.models import SiteSetting
from listings.models import Category, Listing

from . import services
from .models import Booking, Payment


def make_world():
    owner = User.objects.create_user("owner", "o@x.com", "pw12345678", first_name="Olu", payout_account="01711111111")
    renter = User.objects.create_user("renter", "r@x.com", "pw12345678", first_name="Rena")
    cat = Category.objects.create(name="Cameras", slug="cameras")
    listing = Listing.objects.create(
        owner=owner, category=cat, title="Canon 80D", description="Nice camera", price_per_day=1000,
        security_deposit=5000, city="Dhaka", area="Mirpur", delivery_available=True, delivery_fee=200)
    return owner, renter, listing


class LifecycleTests(TestCase):
    def setUp(self):
        self.owner, self.renter, self.listing = make_world()
        self.start = timezone.localdate() + timedelta(days=2)
        self.end = self.start + timedelta(days=2)  # 3 days

    def book(self, **kw):
        return services.create_booking(listing=self.listing, renter=self.renter, start_date=self.start,
                                       end_date=self.end, **kw)

    def test_money_math_uses_commission(self):
        b = self.book(delivery_method="delivery", delivery_address="Banani")
        self.assertEqual(b.days, 3)
        self.assertEqual(b.rental_amount, Decimal("3000.00"))
        self.assertEqual(b.commission_amount, Decimal("300.00"))      # 10%
        self.assertEqual(b.total_payable, Decimal("8200.00"))         # 3000 + 200 + 5000
        self.assertEqual(b.owner_payout, Decimal("2900.00"))          # 3000 + 200 - 300

    def test_cannot_book_own_item_or_overlap(self):
        with self.assertRaises(services.ServiceError):
            services.create_booking(listing=self.listing, renter=self.owner, start_date=self.start, end_date=self.end)
        b = self.book()
        services.accept(b)
        with self.assertRaises(services.ServiceError):
            self.book()

    def test_full_happy_path_with_auto_verify(self):
        b = self.book()
        services.accept(b)
        services.submit_payment(b, method="bkash", trx_id="abc12345", sender="01800000000")
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.PAID)
        self.assertEqual(b.deposit_status, Booking.DepositStatus.HELD)
        services.mark_handed_over(b)
        services.mark_returned(b, Decimal("0"))
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.COMPLETED)
        payout = b.payments.get(kind=Payment.Kind.PAYOUT)
        refund = b.payments.get(kind=Payment.Kind.REFUND)
        self.assertEqual(payout.amount, Decimal("2700.00"))
        self.assertEqual(refund.amount, Decimal("5000.00"))

    def test_manual_verification_when_auto_off(self):
        cfg = SiteSetting.load()
        cfg.auto_verify_payments = False
        cfg.save()
        b = self.book()
        services.accept(b)
        p = services.submit_payment(b, method="nagad", trx_id="TRX99999", sender="01800000000")
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.ACCEPTED)
        services.verify_payment(p)
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.PAID)

    def test_damage_deduction_and_dispute_resolution(self):
        b = self.book()
        services.accept(b)
        services.submit_payment(b, method="bkash", trx_id="ZZZ11111", sender="01800000000")
        services.mark_handed_over(b)
        services.mark_returned(b, Decimal("1500"), "Scratched lens")
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.RETURNED)
        dispute = services.open_dispute(b, self.renter, "deduction", "The scratch was already there before.")
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.DISPUTED)
        services.resolve_dispute(dispute, Decimal("500"), "Split fairly", self.owner)
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.COMPLETED)
        self.assertEqual(b.deposit_status, Booking.DepositStatus.PARTIAL)
        self.assertEqual(b.payments.get(kind=Payment.Kind.REFUND).amount, Decimal("4500.00"))
        self.assertEqual(b.payments.get(kind=Payment.Kind.PAYOUT).amount, Decimal("2700.00") + Decimal("500.00"))

    def test_cancel_paid_creates_full_refund(self):
        b = self.book()
        services.accept(b)
        services.submit_payment(b, method="bkash", trx_id="CAN12345", sender="01800000000")
        services.cancel(b, self.renter, "Plans changed")
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.CANCELLED)
        self.assertEqual(b.payments.get(kind=Payment.Kind.REFUND).amount, b.total_payable)

    def test_duplicate_trx_id_rejected_by_form(self):
        from .forms import PaymentForm
        b = self.book()
        services.accept(b)
        services.submit_payment(b, method="bkash", trx_id="DUP12345", sender="01800000000")
        form = PaymentForm({"method": "bkash", "trx_id": "dup12345", "sender": "01900000000"})
        self.assertFalse(form.is_valid())

    def test_expire_stale(self):
        b = self.book()
        Booking.objects.filter(pk=b.pk).update(created_at=timezone.now() - timedelta(hours=60))
        self.assertEqual(services.expire_stale_bookings()["pending"], 1)


class ViewTests(TestCase):
    def setUp(self):
        self.owner, self.renter, self.listing = make_world()
        self.start = timezone.localdate() + timedelta(days=3)

    def test_listing_page_and_booking_post(self):
        self.client.login(username="renter", password="pw12345678")
        url = self.listing.get_absolute_url()
        self.assertEqual(self.client.get(url).status_code, 200)
        resp = self.client.post(url, {"start_date": self.start, "end_date": self.start + timedelta(days=1),
                                      "delivery_method": "pickup", "delivery_address": "", "message": "hi"})
        booking = Booking.objects.get()
        self.assertRedirects(resp, booking.get_absolute_url())

    def test_booking_permissions(self):
        b = services.create_booking(listing=self.listing, renter=self.renter, start_date=self.start,
                                    end_date=self.start)
        stranger = User.objects.create_user("stranger", "s@x.com", "pw12345678")
        self.client.login(username="stranger", password="pw12345678")
        self.assertEqual(self.client.get(b.get_absolute_url()).status_code, 403)
        self.client.login(username="renter", password="pw12345678")
        self.assertEqual(self.client.post(reverse("bookings:action", args=[b.code, "accept"])).status_code, 403)
        self.client.login(username="owner", password="pw12345678")
        self.client.post(reverse("bookings:action", args=[b.code, "accept"]))
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.ACCEPTED)

    def test_all_pages_render(self):
        b = services.create_booking(listing=self.listing, renter=self.renter, start_date=self.start,
                                    end_date=self.start)
        for name in ("core:home", "core:how_it_works", "core:terms", "core:contact", "listings:list",
                     "accounts:login", "accounts:register"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.client.login(username="renter", password="pw12345678")
        for url in (reverse("accounts:dashboard"), reverse("accounts:profile"), reverse("accounts:verification"),
                    reverse("bookings:list"), reverse("bookings:list") + "?role=owner", b.get_absolute_url(),
                    reverse("bookings:invoice", args=[b.code]), reverse("core:notifications"),
                    reverse("listings:favorites"), reverse("listings:mine"), reverse("listings:create"),
                    reverse("accounts:public_profile", args=["owner"]), reverse("accounts:password_change")):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.client.login(username="owner", password="pw12345678")
        self.assertEqual(self.client.get(reverse("listings:update", args=[self.listing.slug])).status_code, 200)
        self.assertEqual(self.client.get(reverse("listings:delete", args=[self.listing.slug])).status_code, 200)
        self.assertEqual(self.client.get(b.get_absolute_url()).status_code, 200)


class AdminTests(TestCase):
    def test_admin_pages(self):
        owner, renter, listing = make_world()
        start = timezone.localdate() + timedelta(days=3)
        b = services.create_booking(listing=listing, renter=renter, start_date=start, end_date=start)
        User.objects.create_superuser("boss", "boss@x.com", "pw12345678")
        self.client.login(username="boss", password="pw12345678")
        for url in ("/admin/", "/admin/accounts/user/", "/admin/accounts/user/add/", f"/admin/accounts/user/{owner.pk}/change/",
                    "/admin/listings/listing/", f"/admin/listings/listing/{listing.pk}/change/", "/admin/listings/category/",
                    "/admin/bookings/booking/", f"/admin/bookings/booking/{b.pk}/change/", "/admin/bookings/payment/",
                    "/admin/bookings/dispute/", "/admin/bookings/review/", "/admin/core/sitesetting/",
                    "/admin/core/contactmessage/", "/admin/core/notification/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        page = self.client.get("/admin/").content.decode()
        self.assertIn("Commission earned", page)
