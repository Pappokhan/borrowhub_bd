from django.core.management.base import BaseCommand

from bookings.services import expire_stale_bookings


class Command(BaseCommand):
    help = "Cancel stale requests/unpaid bookings and auto-complete silent inspections. Run hourly via cron."

    def handle(self, *args, **options):
        counts = expire_stale_bookings()
        self.stdout.write(self.style.SUCCESS(
            f"Expired {counts['pending']} unanswered, {counts['unpaid']} unpaid; "
            f"auto-completed {counts['inspections']} inspections."))
