from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from urllib.parse import urlparse

from listings.models import Listing


class _Base(Sitemap):
    protocol = urlparse(settings.SITE_URL).scheme or "https"


class StaticSitemap(_Base):
    priority = 0.6
    changefreq = "monthly"

    def items(self):
        return ["core:home", "listings:list", "core:how_it_works", "core:terms", "core:contact"]

    def location(self, item):
        return reverse(item)


class ListingSitemap(_Base):
    priority = 0.8
    changefreq = "daily"

    def items(self):
        return Listing.objects.public().order_by("-updated_at")

    def lastmod(self, obj):
        return obj.updated_at


sitemaps = {"static": StaticSitemap, "listings": ListingSitemap}
