"""Business logic for the rental lifecycle.

pending → accepted → paid → active → returned → completed
              ↘ rejected / cancelled            ↘ disputed → completed
"""
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from core.models import SiteSetting, notify

from .models import Booking, Dispute, Payment

S = Booking.Status
BLOCKING = [S.ACCEPTED, S.PAID, S.ACTIVE]  # statuses that reserve the dates


class ServiceError(Exception):
    pass


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _n(user, text, booking):
    notify(user, text, booking.get_absolute_url())


def is_available(listing, start, end, exclude_pk=None):
    qs = Booking.objects.filter(listing=listing, status__in=BLOCKING, start_date__lte=end, end_date__gte=start)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return not qs.exists()


@transaction.atomic
def create_booking(*, listing, renter, start_date, end_date, delivery_method="pickup",
                   delivery_address="", message=""):
    # Lock the listing row so two renters can't grab the same dates at the same instant (PostgreSQL).
    listing = type(listing).objects.select_for_update().get(pk=listing.pk)
    if listing.owner_id == renter.id:
        raise ServiceError("You can't rent your own item.")
    if listing.status != listing.Status.ACTIVE:
        raise ServiceError("This listing isn't available right now.")
    if not is_available(listing, start_date, end_date):
        raise ServiceError("Those dates are already booked. Please choose different dates.")
    cfg = SiteSetting.load()
    days = (end_date - start_date).days + 1
    rental = money(listing.price_per_day * days)
    delivery_fee = money(listing.delivery_fee) if delivery_method == Booking.Delivery.DELIVERY else money(0)
    commission = money(rental * cfg.commission_percent / 100)
    booking = Booking.objects.create(
        listing=listing, renter=renter, owner=listing.owner, start_date=start_date, end_date=end_date,
        days=days, delivery_method=delivery_method, delivery_address=delivery_address, message=message,
        daily_rate=listing.price_per_day, rental_amount=rental, delivery_fee=delivery_fee,
        security_deposit=money(listing.security_deposit),
        total_payable=rental + delivery_fee + money(listing.security_deposit),
        commission_percent=cfg.commission_percent, commission_amount=commission,
        owner_payout=rental + delivery_fee - commission,
    )
    _n(listing.owner, f"New rental request for “{listing.title}” from {renter.display_name}.", booking)
    return booking


@transaction.atomic
def accept(booking):
    type(booking.listing).objects.select_for_update().get(pk=booking.listing_id)
    Booking.objects.select_for_update().get(pk=booking.pk)
    booking.refresh_from_db()  # keep the caller's object in sync with the locked row
    if booking.status != S.PENDING:
        raise ServiceError("This request is no longer pending.")
    if not is_available(booking.listing, booking.start_date, booking.end_date, exclude_pk=booking.pk):
        raise ServiceError("These dates were booked by someone else in the meantime.")
    booking.status = S.ACCEPTED
    booking.accepted_at = timezone.now()
    booking.save(update_fields=["status", "accepted_at"])
    hours = SiteSetting.load().payment_window_hours
    _n(booking.renter, f"Request accepted! Pay within {hours} hours to confirm “{booking.listing.title}”.", booking)


@transaction.atomic
def reject(booking, reason=""):
    if booking.status != S.PENDING:
        raise ServiceError("This request is no longer pending.")
    booking.status = S.REJECTED
    booking.cancel_reason = reason[:255]
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancel_reason", "cancelled_at"])
    _n(booking.renter, f"The owner declined your request for “{booking.listing.title}”.", booking)


@transaction.atomic
def cancel(booking, by=None, reason=""):
    if booking.status not in (S.PENDING, S.ACCEPTED, S.PAID):
        raise ServiceError("This booking can no longer be cancelled.")
    was_paid = booking.status == S.PAID
    booking.status = S.CANCELLED
    booking.cancelled_by = by
    booking.cancel_reason = reason[:255]
    booking.cancelled_at = timezone.now()
    if was_paid:
        booking.deposit_status = Booking.DepositStatus.REFUNDED
        paid = booking.payments.filter(kind=Payment.Kind.COLLECTION, status=Payment.Status.COMPLETED).first()
        Payment.objects.create(
            booking=booking, kind=Payment.Kind.REFUND, amount=booking.total_payable,
            method=paid.method if paid else Payment.Method.BKASH, account=paid.account if paid else "",
            note="Booking cancelled — full refund")
    booking.payments.filter(kind=Payment.Kind.COLLECTION, status=Payment.Status.PENDING).update(
        status=Payment.Status.FAILED, note="Booking cancelled")
    booking.save()
    for party in (booking.renter, booking.owner):
        if by is None or party.id != by.id:
            _n(party, f"Booking {booking.code} was cancelled." + (" Refund is being processed." if was_paid else ""), booking)


@transaction.atomic
def submit_payment(booking, *, method, trx_id, sender):
    if booking.status != S.ACCEPTED:
        raise ServiceError("This booking isn't waiting for payment.")
    if booking.payments.filter(kind=Payment.Kind.COLLECTION, status=Payment.Status.PENDING).exists():
        raise ServiceError("Your payment is already being verified.")
    payment = Payment.objects.create(
        booking=booking, kind=Payment.Kind.COLLECTION, method=method, amount=booking.total_payable,
        trx_id=trx_id.strip().upper(), account=sender)
    if SiteSetting.load().auto_verify_payments:
        verify_payment(payment, by=None)
    else:
        for staff in User.objects.filter(is_staff=True, is_active=True):
            notify(staff, f"Payment {payment.trx_id} for {booking.code} needs verification.", reverse("admin:bookings_payment_changelist"))
        _n(booking.renter, "Payment received — we're verifying your transaction ID. This usually takes under an hour.", booking)
    return payment


@transaction.atomic
def verify_payment(payment, by=None):
    booking = payment.booking
    if payment.kind != Payment.Kind.COLLECTION:
        raise ServiceError("Only incoming payments can be verified.")
    if booking.status != S.ACCEPTED:
        raise ServiceError(f"{booking.code} is {booking.get_status_display().lower()} — can't verify.")
    payment.status = Payment.Status.COMPLETED
    payment.processed_at = timezone.now()
    payment.processed_by = by
    payment.save(update_fields=["status", "processed_at", "processed_by"])
    booking.status = S.PAID
    booking.paid_at = timezone.now()
    booking.deposit_status = Booking.DepositStatus.HELD
    booking.save(update_fields=["status", "paid_at", "deposit_status"])
    _n(booking.renter, f"Payment confirmed for “{booking.listing.title}”. Arrange the handover with the owner.", booking)
    _n(booking.owner, f"{booking.renter.display_name} has paid for “{booking.listing.title}”. Get the item ready!", booking)


@transaction.atomic
def reject_payment(payment, by=None, note="Transaction could not be verified"):
    if payment.kind != Payment.Kind.COLLECTION or payment.status != Payment.Status.PENDING:
        raise ServiceError("Only pending incoming payments can be rejected.")
    payment.status = Payment.Status.FAILED
    payment.note = note
    payment.processed_at = timezone.now()
    payment.processed_by = by
    payment.save(update_fields=["status", "note", "processed_at", "processed_by"])
    _n(payment.booking.renter, f"We couldn't verify transaction {payment.trx_id}. Please check and pay again.", payment.booking)


@transaction.atomic
def mark_handed_over(booking):
    if booking.status != S.PAID:
        raise ServiceError("Payment must be confirmed before handover.")
    booking.status = S.ACTIVE
    booking.handed_over_at = timezone.now()
    booking.save(update_fields=["status", "handed_over_at"])
    _n(booking.renter, f"Handover confirmed — enjoy “{booking.listing.title}”! Return it by {booking.end_date:%d %b}.", booking)


@transaction.atomic
def mark_returned(booking, deduction=Decimal("0"), note=""):
    if booking.status != S.ACTIVE:
        raise ServiceError("Only items that are on rent can be marked as returned.")
    deduction = money(deduction or 0)
    if deduction < 0 or deduction > booking.security_deposit:
        raise ServiceError("The deduction can't be more than the security deposit.")
    booking.status = S.RETURNED
    booking.returned_at = timezone.now()
    booking.deposit_deduction = deduction
    booking.inspection_note = note
    booking.save(update_fields=["status", "returned_at", "deposit_deduction", "inspection_note"])
    if deduction == 0:
        complete(booking)
    else:
        hours = SiteSetting.load().inspection_window_hours
        _n(booking.renter, f"The owner reported ৳{deduction} in damages. Accept or dispute within {hours} hours.", booking)


@transaction.atomic
def accept_inspection(booking):
    if booking.status != S.RETURNED:
        raise ServiceError("There's nothing to accept right now.")
    complete(booking)


@transaction.atomic
def complete(booking, deduction=None):
    if booking.status not in (S.RETURNED, S.DISPUTED):
        raise ServiceError("This booking can't be completed yet.")
    if deduction is not None:
        deduction = money(deduction)
        if deduction < 0 or deduction > booking.security_deposit:
            raise ServiceError("The deduction can't be more than the security deposit.")
        booking.deposit_deduction = deduction
    ded, deposit = booking.deposit_deduction, booking.security_deposit
    booking.status = S.COMPLETED
    booking.completed_at = timezone.now()
    booking.returned_at = booking.returned_at or booking.completed_at
    if deposit == 0:
        booking.deposit_status = Booking.DepositStatus.UNPAID
    elif ded >= deposit:
        booking.deposit_status = Booking.DepositStatus.FORFEITED
    elif ded > 0:
        booking.deposit_status = Booking.DepositStatus.PARTIAL
    else:
        booking.deposit_status = Booking.DepositStatus.REFUNDED
    booking.save()

    paid = booking.payments.filter(kind=Payment.Kind.COLLECTION, status=Payment.Status.COMPLETED).first()
    owner_total = booking.owner_payout + ded
    Payment.objects.get_or_create(
        booking=booking, kind=Payment.Kind.PAYOUT,
        defaults=dict(amount=owner_total, method=booking.owner.payout_method,
                      account=booking.owner.payout_account, note="Rental earnings (after commission)"
                      + (f" + ৳{ded} deposit deduction" if ded else "")))
    refund = deposit - ded
    if refund > 0:
        Payment.objects.get_or_create(
            booking=booking, kind=Payment.Kind.REFUND,
            defaults=dict(amount=refund, method=paid.method if paid else Payment.Method.BKASH,
                          account=paid.account if paid else "", note="Security deposit refund"))
    _n(booking.renter, f"Rental complete! ৳{refund} deposit refund is on its way. Please leave a review.", booking)
    _n(booking.owner, f"Rental complete! ৳{owner_total} will be sent to your payout account. Please leave a review.", booking)


@transaction.atomic
def open_dispute(booking, user, reason, details):
    if booking.status not in (S.ACTIVE, S.RETURNED):
        raise ServiceError("A dispute can only be opened while the item is on rent or awaiting inspection.")
    booking.status = S.DISPUTED
    booking.save(update_fields=["status"])
    dispute = Dispute.objects.create(booking=booking, raised_by=user, reason=reason, details=details)
    _n(booking.other_party(user), f"A dispute was opened on booking {booking.code}. Our team will review it.", booking)
    for staff in User.objects.filter(is_staff=True, is_active=True):
        notify(staff, f"Dispute opened on {booking.code}.", reverse("admin:bookings_dispute_changelist"))
    return dispute


@transaction.atomic
def resolve_dispute(dispute, final_deduction, note, admin_user):
    booking = dispute.booking
    if booking.status == S.DISPUTED:
        complete(booking, deduction=final_deduction)
    dispute.status = Dispute.Status.RESOLVED
    dispute.final_deduction = money(final_deduction)
    dispute.resolution_note = note
    dispute.resolved_by = admin_user
    dispute.resolved_at = timezone.now()
    dispute.save()


def expire_stale_bookings():
    """Run periodically (cron): drops unanswered/unpaid requests and auto-accepts silent inspections."""
    now, cfg = timezone.now(), SiteSetting.load()
    counts = {"pending": 0, "unpaid": 0, "inspections": 0}
    for b in Booking.objects.filter(status=S.PENDING, created_at__lt=now - timedelta(hours=48)):
        cancel(b, None, "Owner did not respond in 48 hours")
        counts["pending"] += 1
    unpaid = Booking.objects.filter(status=S.ACCEPTED, accepted_at__lt=now - timedelta(hours=cfg.payment_window_hours))
    for b in unpaid:
        if not b.payments.filter(kind=Payment.Kind.COLLECTION, status=Payment.Status.PENDING).exists():
            cancel(b, None, "Payment window expired")
            counts["unpaid"] += 1
    stale = Booking.objects.filter(status=S.RETURNED, returned_at__lt=now - timedelta(hours=cfg.inspection_window_hours))
    for b in stale:
        complete(b)
        counts["inspections"] += 1
    return counts
