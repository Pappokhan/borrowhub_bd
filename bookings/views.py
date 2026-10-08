from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import SiteSetting

from . import services
from .forms import DisputeForm, InspectionForm, PaymentForm, ReviewForm
from .models import Booking, Payment, Review

STEPS = [(0, "Requested"), (1, "Accepted"), (2, "Paid"), (3, "On rent"), (4, "Returned"), (5, "Completed")]


def _get_booking(user, code):
    booking = get_object_or_404(
        Booking.objects.select_related("listing", "renter", "owner").prefetch_related("listing__images"), code=code)
    if not (user.is_staff or user.id in (booking.renter_id, booking.owner_id)):
        raise PermissionDenied
    return booking


def _form_errors(request, form):
    for field, errs in form.errors.items():
        label = form.fields[field].label if field in form.fields else ""
        for e in errs:
            messages.error(request, f"{label + ': ' if label else ''}{e}")


@login_required
def booking_list(request):
    role = "owner" if request.GET.get("role") == "owner" else "renter"
    status = request.GET.get("status", "")
    base = Booking.objects.filter(**{role: request.user}).select_related("listing", "renter", "owner") \
        .prefetch_related("listing__images")
    qs = base.filter(status=status) if status in Booking.Status.values else base
    counts = {
        "renter": Booking.objects.filter(renter=request.user).count(),
        "owner": Booking.objects.filter(owner=request.user).count(),
    }
    return render(request, "bookings/list.html", {
        "bookings": qs, "role": role, "status": status, "counts": counts,
        "statuses": Booking.Status.choices})


@login_required
def booking_detail(request, code):
    booking = _get_booking(request.user, code)
    user = request.user
    is_owner, is_renter = booking.owner_id == user.id, booking.renter_id == user.id
    S = Booking.Status
    pending_payment = booking.payments.filter(kind=Payment.Kind.COLLECTION, status=Payment.Status.PENDING).first()
    my_review = booking.reviews.filter(reviewer=user).first()
    ctx = {
        "booking": booking, "is_owner": is_owner, "is_renter": is_renter, "steps": STEPS,
        "pending_payment": pending_payment, "payments": booking.payments.all() if (is_owner or is_renter or user.is_staff) else [],
        "pay_numbers": SiteSetting.load().payment_numbers(),
        "pay_form": PaymentForm() if is_renter and booking.status == S.ACCEPTED and not pending_payment else None,
        "inspection_form": InspectionForm() if is_owner and booking.status == S.ACTIVE else None,
        "dispute_form": DisputeForm() if (is_owner or is_renter) and booking.status in (S.ACTIVE, S.RETURNED) else None,
        "review_form": ReviewForm() if (is_owner or is_renter) and booking.status == S.COMPLETED and not my_review else None,
        "my_review": my_review,
        "reviews": booking.reviews.select_related("reviewer"),
        "disputes": booking.disputes.select_related("raised_by"),
    }
    return render(request, "bookings/detail.html", ctx)


@login_required
@require_POST
def booking_action(request, code, action):
    booking = _get_booking(request.user, code)
    user = request.user
    is_owner, is_renter = booking.owner_id == user.id, booking.renter_id == user.id
    try:
        if action == "accept" and is_owner:
            services.accept(booking)
            messages.success(request, "Request accepted. The renter has been asked to pay.")
        elif action == "reject" and is_owner:
            services.reject(booking, request.POST.get("reason", ""))
            messages.info(request, "Request declined.")
        elif action == "cancel" and (is_owner or is_renter):
            services.cancel(booking, user, request.POST.get("reason", ""))
            messages.info(request, "Booking cancelled.")
        elif action == "pay" and is_renter:
            form = PaymentForm(request.POST)
            if form.is_valid():
                services.submit_payment(booking, method=form.cleaned_data["method"],
                                        trx_id=form.cleaned_data["trx_id"], sender=form.cleaned_data["sender"])
                booking.refresh_from_db()
                if booking.status == Booking.Status.PAID:
                    messages.success(request, "Payment confirmed! Contact the owner to arrange the handover.")
                else:
                    messages.success(request, "Payment submitted. We're verifying your transaction ID.")
            else:
                _form_errors(request, form)
        elif action == "handover" and is_owner:
            services.mark_handed_over(booking)
            messages.success(request, "Marked as handed over.")
        elif action == "return" and is_owner:
            form = InspectionForm(request.POST)
            if form.is_valid():
                services.mark_returned(booking, form.cleaned_data["deduction"], form.cleaned_data["note"])
                messages.success(request, "Return recorded.")
            else:
                _form_errors(request, form)
        elif action == "accept-inspection" and is_renter:
            services.accept_inspection(booking)
            messages.success(request, "Thanks — the rental is complete.")
        elif action == "dispute" and (is_owner or is_renter):
            form = DisputeForm(request.POST)
            if form.is_valid():
                services.open_dispute(booking, user, form.cleaned_data["reason"], form.cleaned_data["details"])
                messages.warning(request, "Dispute opened. Our team will review and contact you both.")
            else:
                _form_errors(request, form)
        elif action == "review" and (is_owner or is_renter):
            form = ReviewForm(request.POST)
            if booking.status != Booking.Status.COMPLETED:
                messages.error(request, "You can review once the rental is complete.")
            elif booking.reviews.filter(reviewer=user).exists():
                messages.error(request, "You've already reviewed this booking.")
            elif form.is_valid():
                Review.objects.create(
                    booking=booking, reviewer=user, reviewee=booking.other_party(user), listing=booking.listing,
                    direction=Review.Direction.FOR_OWNER if is_renter else Review.Direction.FOR_RENTER,
                    rating=form.cleaned_data["rating"], comment=form.cleaned_data["comment"])
                messages.success(request, "Review posted. Thank you!")
            else:
                _form_errors(request, form)
        else:
            raise PermissionDenied
    except services.ServiceError as exc:
        messages.error(request, str(exc))
    return redirect(booking)


@login_required
def booking_invoice(request, code):
    booking = _get_booking(request.user, code)
    return render(request, "bookings/invoice.html", {"booking": booking})
