from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings import services
from bookings.tests import make_world


class ListingSearchTests(TestCase):
    def setUp(self):
        self.owner, self.renter, self.listing = make_world()

    def test_search_and_filters(self):
        url = reverse("listings:list")
        self.assertContains(self.client.get(url, {"q": "canon"}), "Canon 80D")
        self.assertNotContains(self.client.get(url, {"q": "nothing-here"}), "Canon 80D")
        self.assertNotContains(self.client.get(url, {"city": "Sylhet"}), "Canon 80D")
        self.assertContains(self.client.get(url, {"min_price": "500", "max_price": "1500", "delivery": "1"}), "Canon 80D")
        self.assertEqual(self.client.get(url, {"min_price": "abc", "start": "bad", "end": "date"}).status_code, 200)

    def test_availability_filter_hides_booked(self):
        start = timezone.localdate() + timedelta(days=5)
        b = services.create_booking(listing=self.listing, renter=self.renter, start_date=start, end_date=start)
        services.accept(b)
        url = reverse("listings:list")
        self.assertNotContains(self.client.get(url, {"start": start, "end": start}), "Canon 80D")
        self.assertContains(self.client.get(url, {"start": start + timedelta(days=3), "end": start + timedelta(days=4)}),
                            "Canon 80D")

    def test_paused_listing_hidden_from_public(self):
        self.listing.status = "paused"
        self.listing.save()
        self.assertEqual(self.client.get(self.listing.get_absolute_url()).status_code, 404)
