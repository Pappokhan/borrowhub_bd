from django.contrib.admin.apps import AdminConfig


class BorrowAdminConfig(AdminConfig):
    """Swap Django's default admin site for the BorrowHub dashboard site."""

    default_site = "core.sites.BorrowHubAdminSite"
