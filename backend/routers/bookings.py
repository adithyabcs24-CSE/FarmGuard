import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    User,
    Booking,
    ProviderProfile,
    ProviderService,
    AvailabilitySlot,
    Address,
    Invoice,
    Review,
    Complaint,
    ServiceCategory,
    ChatMessage,
    AdditionalCharge
)
from backend.schemas import (
    BookingCreateRequest,
    BookingStatusUpdateRequest,
    BookingResponse,
    BookingDetailResponse,
    InvoiceResponse,
    ReviewCreateRequest,
    ReviewResponse,
    MessageResponse,
    QuoteRequestCreate,
    QuoteAcceptResponse,
    ComplaintCreateRequest,
    ComplaintResponse,
    ProviderLocationUpdateRequest,
    BookingTrackingResponse,
    ChatMessageCreateRequest,
    ChatMessageResponse,
    AdditionalChargeCreateRequest,
    AdditionalChargeActionRequest,
    AdditionalChargeResponse,
    EmergencyBookingCreateRequest
)
from backend.auth import get_current_user, require_role
from backend.utils import get_day_name, add_notification, haversine_distance_km

router = APIRouter(prefix="/api/bookings", tags=["bookings"])

# Valid sequential transitions
ALLOWED_TRANSITIONS = {
    "REQUESTED": ["ACCEPTED", "CANCELLED"],
    "ACCEPTED": ["ON_THE_WAY", "CANCELLED"],
    "ON_THE_WAY": ["ARRIVED"],
    "ARRIVED": ["IN_PROGRESS"],
    "IN_PROGRESS": ["COMPLETED"],
    "COMPLETED": [],
    "CANCELLED": []
}


def times_overlap(time_a: str, time_b: str) -> bool:
    """Check if two 1-hour slot windows overlap."""
    try:
        hour_a = int(time_a.split(":")[0])
        hour_b = int(time_b.split(":")[0])
        return abs(hour_a - hour_b) < 1
    except Exception:
        return time_a == time_b


def check_provider_availability(
    provider_id: int,
    scheduled_date: str,
    scheduled_time: str,
    db: Session
) -> bool:
    """Verify provider has an active availability slot matching the date and time."""
    day_name = get_day_name(scheduled_date)
    slots = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.provider_id == provider_id,
        AvailabilitySlot.day_of_week == day_name
    ).all()

    if not slots:
        return False

    try:
        req_hour = int(scheduled_time.split(":")[0])
        req_min = int(scheduled_time.split(":")[1])
        req_minutes = req_hour * 60 + req_min

        for slot in slots:
            start_h, start_m = map(int, slot.start_time.split(":"))
            end_h, end_m = map(int, slot.end_time.split(":"))
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            # Slot window is typically 1 hour
            if start_minutes <= req_minutes and (req_minutes + 60) <= end_minutes:
                return True
    except Exception:
        return True

    return False


def check_double_booking(
    provider_id: int,
    scheduled_date: str,
    scheduled_time: str,
    db: Session,
    exclude_booking_id: int = None
) -> bool:
    active_statuses = ["ACCEPTED", "ON_THE_WAY", "ARRIVED", "IN_PROGRESS"]
    query = db.query(Booking).filter(
        Booking.provider_id == provider_id,
        Booking.scheduled_date == scheduled_date,
        Booking.status.in_(active_statuses)
    )
    if exclude_booking_id:
        query = query.filter(Booking.id != exclude_booking_id)

    existing_bookings = query.all()
    for b in existing_bookings:
        if times_overlap(b.scheduled_time, scheduled_time):
            return True
    return False


def cancel_quote_siblings(booking: Booking, db: Session) -> List[int]:
    """
    If booking has a [Quote Ref: ...], find and cancel all sibling bookings in REQUESTED status.
    Returns the list of cancelled booking IDs.
    """
    cancelled_ids = []
    if not booking.problem_description:
        return cancelled_ids

    m = re.search(r"\[Quote Ref:\s*([^\]]+)\]", booking.problem_description)
    if not m:
        return cancelled_ids

    quote_ref = m.group(1).strip()
    siblings = db.query(Booking).filter(
        Booking.id != booking.id,
        Booking.customer_id == booking.customer_id,
        Booking.problem_description.like(f"%[Quote Ref: {quote_ref}]%"),
        Booking.status == "REQUESTED"
    ).all()

    for sib in siblings:
        sib.status = "CANCELLED"
        sib.cancellation_reason = f"[Quote Declined] Quote #{booking.id} was accepted."
        cancelled_ids.append(sib.id)
        # Notify the affected provider
        add_notification(
            sib.provider_id,
            f"Quote request #{sib.id} was automatically closed as the customer selected another provider.",
            db
        )

    return cancelled_ids


# -------------------------------------------------------------
# Standard Booking Creation
# -------------------------------------------------------------
@router.post("", response_model=BookingResponse)
def create_booking(
    payload: BookingCreateRequest,
    current_user: User = Depends(require_role(["customer", "admin"])),
    db: Session = Depends(get_db)
):
    provider = db.query(User).filter(User.id == payload.provider_id, User.role == "provider").first()
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found"
        )

    # Check if provider is suspended / rejected
    if provider.profile and provider.profile.verification_status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This provider is suspended or not authorized to accept bookings."
        )

    service = db.query(ProviderService).filter(
        ProviderService.id == payload.service_id,
        ProviderService.provider_id == payload.provider_id
    ).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected service does not belong to the selected provider"
        )

    if service.category_id != payload.category_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service does not match the specified category"
        )

    if not check_provider_availability(payload.provider_id, payload.scheduled_date, payload.scheduled_time, db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider is not available on {get_day_name(payload.scheduled_date)} at {payload.scheduled_time}. Please select an available slot."
        )

    if check_double_booking(payload.provider_id, payload.scheduled_date, payload.scheduled_time, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider is already booked for this date and time slot."
        )

    address_id = payload.address_id
    if not address_id:
        if not payload.new_full_address:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Address must be selected or full address must be provided"
            )
        new_addr = Address(
            user_id=current_user.id,
            label=payload.new_address_label or "Home",
            full_address=payload.new_full_address,
            latitude=payload.new_latitude or 12.9716,
            longitude=payload.new_longitude or 77.5946
        )
        db.add(new_addr)
        db.commit()
        db.refresh(new_addr)
        address_id = new_addr.id
    else:
        addr = db.query(Address).filter(Address.id == address_id).first()
        if not addr:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Address not found"
            )

    desc = payload.problem_description
    if payload.recurring_interval:
        desc += f" [Recurring: {payload.recurring_interval}]"

    booking = Booking(
        customer_id=current_user.id,
        provider_id=payload.provider_id,
        category_id=payload.category_id,
        service_id=payload.service_id,
        address_id=address_id,
        problem_description=desc,
        photo_url=payload.photo_url,
        scheduled_date=payload.scheduled_date,
        scheduled_time=payload.scheduled_time,
        status="REQUESTED",
        price_estimate_min=service.price_min,
        price_estimate_max=service.price_max,
        final_price=None,
        cancellation_reason=None,
        created_at=datetime.now(timezone.utc)
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # NOTIFICATION: New booking request -> provider
    add_notification(
        booking.provider_id,
        f"New booking request #{booking.id} received from {current_user.name} for {service.service_name} on {booking.scheduled_date} at {booking.scheduled_time}.",
        db
    )

    return BookingResponse.model_validate(booking)


# -------------------------------------------------------------
# Multi-Provider Quote Requests
# -------------------------------------------------------------
@router.post("/quotes", response_model=List[BookingResponse])
def create_quote_requests(
    payload: QuoteRequestCreate,
    current_user: User = Depends(require_role(["customer", "admin"])),
    db: Session = Depends(get_db)
):
    address_id = payload.address_id
    if not address_id:
        if not payload.new_full_address:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Address must be selected or full address must be provided"
            )
        new_addr = Address(
            user_id=current_user.id,
            label=payload.new_address_label or "Home",
            full_address=payload.new_full_address,
            latitude=payload.new_latitude or 12.9716,
            longitude=payload.new_longitude or 77.5946
        )
        db.add(new_addr)
        db.commit()
        db.refresh(new_addr)
        address_id = new_addr.id
    else:
        addr = db.query(Address).filter(Address.id == address_id).first()
        if not addr:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Address not found"
            )

    quote_group_id = f"QR-{uuid.uuid4().hex[:8].upper()}"
    full_description = f"[Quote Ref: {quote_group_id}] {payload.problem_description}"

    created_bookings: List[Booking] = []

    for prov_id in payload.provider_ids:
        provider = db.query(User).filter(User.id == prov_id, User.role == "provider").first()
        if not provider:
            continue
        # Skip suspended providers
        if provider.profile and provider.profile.verification_status == "rejected":
            continue

        # Find service in this category for provider
        service = db.query(ProviderService).filter(
            ProviderService.provider_id == prov_id,
            ProviderService.category_id == payload.category_id
        ).first()

        # Fallback to any service for provider if category service not found
        if not service:
            service = db.query(ProviderService).filter(ProviderService.provider_id == prov_id).first()

        if not service:
            continue

        b = Booking(
            customer_id=current_user.id,
            provider_id=prov_id,
            category_id=payload.category_id,
            service_id=service.id,
            address_id=address_id,
            problem_description=full_description,
            photo_url=None,
            scheduled_date=payload.scheduled_date,
            scheduled_time=payload.scheduled_time,
            status="REQUESTED",
            price_estimate_min=service.price_min,
            price_estimate_max=service.price_max,
            final_price=None,
            cancellation_reason=None,
            created_at=datetime.now(timezone.utc)
        )
        db.add(b)
        db.commit()
        db.refresh(b)
        created_bookings.append(b)

        # Notify provider
        add_notification(
            prov_id,
            f"New quote request #{b.id} received from {current_user.name} for {service.service_name} on {b.scheduled_date} at {b.scheduled_time}.",
            db
        )

    if not created_bookings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not create quote requests for the selected providers"
        )

    return [BookingResponse.model_validate(b) for b in created_bookings]


# -------------------------------------------------------------
# Emergency Booking Broadcast
# -------------------------------------------------------------
@router.post("/emergency", response_model=List[BookingResponse])
def create_emergency_booking(
    payload: EmergencyBookingCreateRequest,
    current_user: User = Depends(require_role(["customer", "admin"])),
    db: Session = Depends(get_db)
):
    """
    Broadcasts an emergency request to all verified, in-radius, non-suspended providers
    for the specified category simultaneously.
    """
    address_id = payload.address_id
    if not address_id:
        if not payload.new_full_address:
            raise HTTPException(400, "Must provide address or saved address ID")
        new_addr = Address(
            user_id=current_user.id,
            label=payload.new_address_label or "Home",
            full_address=payload.new_full_address,
            latitude=payload.new_latitude or 12.9716,
            longitude=payload.new_longitude or 77.5946
        )
        db.add(new_addr)
        db.commit()
        db.refresh(new_addr)
        address_id = new_addr.id
        cust_lat = new_addr.latitude
        cust_lon = new_addr.longitude
    else:
        addr = db.query(Address).filter(Address.id == address_id).first()
        if not addr:
            raise HTTPException(404, "Address not found")
        cust_lat = addr.latitude or 12.9716
        cust_lon = addr.longitude or 77.5946

    category = db.query(ServiceCategory).filter(ServiceCategory.id == payload.category_id).first()
    if not category:
        raise HTTPException(404, "Category not found")

    # Find matching verified providers
    providers = db.query(User).filter(User.role == "provider").all()
    matching_candidates = []
    for p in providers:
        prof = p.profile
        if not prof or prof.verification_status != "approved":
            continue
        svc = db.query(ProviderService).filter(
            ProviderService.provider_id == p.id,
            ProviderService.category_id == payload.category_id
        ).first()
        if not svc:
            continue

        if prof.latitude and prof.longitude:
            dist = haversine_distance_km(cust_lat, cust_lon, prof.latitude, prof.longitude)
            if dist > prof.service_radius_km:
                continue
        matching_candidates.append((p, svc))

    # Fallback to any verified provider in category
    if not matching_candidates:
        for p in providers:
            prof = p.profile
            if prof and prof.verification_status == "approved":
                svc = db.query(ProviderService).filter(
                    ProviderService.provider_id == p.id,
                    ProviderService.category_id == payload.category_id
                ).first()
                if svc:
                    matching_candidates.append((p, svc))

    if not matching_candidates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No verified providers currently available for emergency broadcast in this category"
        )

    eb_ref = f"EB-{uuid.uuid4().hex[:8].upper()}"
    full_desc = f"[EMERGENCY BROADCAST: {eb_ref}] {payload.problem_description}"
    today_str = datetime.now().date().strftime("%Y-%m-%d")
    time_now_str = datetime.now().strftime("%H:%M")

    created_emergency = []
    for p, svc in matching_candidates:
        eb = Booking(
            customer_id=current_user.id,
            provider_id=p.id,
            category_id=payload.category_id,
            service_id=svc.id,
            address_id=address_id,
            problem_description=full_desc,
            photo_url=None,
            scheduled_date=today_str,
            scheduled_time=time_now_str,
            status="REQUESTED",
            price_estimate_min=svc.price_min,
            price_estimate_max=svc.price_max,
            final_price=None,
            cancellation_reason=None,
            created_at=datetime.now(timezone.utc)
        )
        db.add(eb)
        db.commit()
        db.refresh(eb)
        created_emergency.append(eb)

        add_notification(
            p.id,
            f"🚨 EMERGENCY REQUEST #{eb.id} in {category.name} from {current_user.name}! First to accept gets the job.",
            db
        )

    return [BookingResponse.model_validate(b) for b in created_emergency]


# -------------------------------------------------------------
# Accept Quote / Accept Action
# -------------------------------------------------------------
@router.post("/{booking_id}/accept-quote", response_model=QuoteAcceptResponse)
def accept_quote(
    booking_id: int,
    current_user: User = Depends(require_role(["customer", "admin"])),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if current_user.role != "admin" and booking.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only accept quotes for your own requests")

    if booking.status != "REQUESTED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot accept quote with status {booking.status}. Only REQUESTED bookings can be accepted.")

    if check_double_booking(booking.provider_id, booking.scheduled_date, booking.scheduled_time, db, exclude_booking_id=booking.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provider is already booked for this date and time.")

    booking.status = "ACCEPTED"
    cancelled_ids = cancel_quote_siblings(booking, db)

    add_notification(
        booking.provider_id,
        f"Customer {current_user.name} accepted your quote for booking #{booking.id}! The job is now confirmed.",
        db
    )
    add_notification(
        current_user.id,
        f"You accepted the quote from {booking.provider.name} for booking #{booking.id}.",
        db
    )

    db.commit()
    db.refresh(booking)

    return QuoteAcceptResponse(
        accepted_booking=BookingResponse.model_validate(booking),
        cancelled_sibling_ids=cancelled_ids,
        message=f"Quote accepted successfully. {len(cancelled_ids)} competing quote requests were automatically cancelled."
    )


# -------------------------------------------------------------
# Booking Retrieval
# -------------------------------------------------------------
@router.get("/my", response_model=List[BookingDetailResponse])
def get_my_bookings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role == "customer":
        bookings = db.query(Booking).filter(
            Booking.customer_id == current_user.id
        ).order_by(Booking.created_at.desc()).all()
    elif current_user.role == "provider":
        bookings = db.query(Booking).filter(
            Booking.provider_id == current_user.id
        ).order_by(Booking.created_at.desc()).all()
    else:  # Admin
        bookings = db.query(Booking).order_by(Booking.created_at.desc()).all()

    results: List[BookingDetailResponse] = []
    for b in bookings:
        inv = InvoiceResponse.model_validate(b.invoice) if b.invoice else None
        rev = None
        if b.review:
            rev = ReviewResponse(
                id=b.review.id,
                booking_id=b.review.booking_id,
                customer_id=b.review.customer_id,
                customer_name=b.customer.name if b.customer else "Customer",
                provider_id=b.review.provider_id,
                rating=b.review.rating,
                comment=b.review.comment,
                created_at=b.review.created_at
            )

        charges = [
            AdditionalChargeResponse.model_validate(c) for c in b.additional_charges
        ] if b.additional_charges else []

        results.append(
            BookingDetailResponse(
                id=b.id,
                customer_id=b.customer_id,
                customer_name=b.customer.name if b.customer else "Unknown",
                customer_phone=b.customer.phone if b.customer else None,
                provider_id=b.provider_id,
                provider_name=b.provider.name if b.provider else "Unknown",
                provider_phone=b.provider.phone if b.provider else None,
                category_id=b.category_id,
                category_name=b.category.name if b.category else "Unknown",
                service_id=b.service_id,
                service_name=b.service.service_name if b.service else "Unknown",
                address_id=b.address_id,
                address_label=b.address.label if b.address else "Address",
                full_address=b.address.full_address if b.address else "",
                latitude=b.address.latitude if b.address else None,
                longitude=b.address.longitude if b.address else None,
                problem_description=b.problem_description,
                photo_url=b.photo_url,
                scheduled_date=b.scheduled_date,
                scheduled_time=b.scheduled_time,
                status=b.status,
                price_estimate_min=b.price_estimate_min,
                price_estimate_max=b.price_estimate_max,
                final_price=b.final_price,
                cancellation_reason=getattr(b, "cancellation_reason", None),
                created_at=b.created_at,
                invoice=inv,
                review=rev,
                additional_charges=charges
            )
        )
    return results


@router.get("/{booking_id}", response_model=BookingDetailResponse)
def get_booking_by_id(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )

    if current_user.role != "admin" and booking.customer_id != current_user.id and booking.provider_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this booking"
        )

    inv = InvoiceResponse.model_validate(booking.invoice) if booking.invoice else None
    rev = None
    if booking.review:
        rev = ReviewResponse(
            id=booking.review.id,
            booking_id=booking.review.booking_id,
            customer_id=booking.review.customer_id,
            customer_name=booking.customer.name if booking.customer else "Customer",
            provider_id=booking.review.provider_id,
            rating=booking.review.rating,
            comment=booking.review.comment,
            created_at=booking.review.created_at
        )

    charges = [
        AdditionalChargeResponse.model_validate(c) for c in booking.additional_charges
    ] if booking.additional_charges else []

    return BookingDetailResponse(
        id=booking.id,
        customer_id=booking.customer_id,
        customer_name=booking.customer.name if booking.customer else "Unknown",
        customer_phone=booking.customer.phone if booking.customer else None,
        provider_id=booking.provider_id,
        provider_name=booking.provider.name if booking.provider else "Unknown",
        provider_phone=booking.provider.phone if booking.provider else None,
        category_id=booking.category_id,
        category_name=booking.category.name if booking.category else "Unknown",
        service_id=booking.service_id,
        service_name=booking.service.service_name if booking.service else "Unknown",
        address_id=booking.address_id,
        address_label=booking.address.label if booking.address else "Address",
        full_address=booking.address.full_address if booking.address else "",
        latitude=booking.address.latitude if booking.address else None,
        longitude=booking.address.longitude if booking.address else None,
        problem_description=booking.problem_description,
        photo_url=booking.photo_url,
        scheduled_date=booking.scheduled_date,
        scheduled_time=booking.scheduled_time,
        status=booking.status,
        price_estimate_min=booking.price_estimate_min,
        price_estimate_max=booking.price_estimate_max,
        final_price=booking.final_price,
        cancellation_reason=getattr(booking, "cancellation_reason", None),
        created_at=booking.created_at,
        invoice=inv,
        review=rev,
        additional_charges=charges
    )


# -------------------------------------------------------------
# Status Transition & Invoice Generation
# -------------------------------------------------------------
@router.put("/{booking_id}/status", response_model=BookingResponse)
def update_booking_status(
    booking_id: int,
    payload: BookingStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )

    current_status = booking.status
    target_status = payload.status

    is_customer_accepting_quote = (
        current_user.role == "customer"
        and booking.customer_id == current_user.id
        and current_status == "REQUESTED"
        and target_status == "ACCEPTED"
    )

    if target_status == "CANCELLED":
        if current_user.role == "customer":
            if booking.customer_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to cancel this booking"
                )
            if current_status not in ["REQUESTED", "ACCEPTED"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot cancel booking once it is {current_status}. Cancellation is only allowed when REQUESTED or ACCEPTED."
                )
        elif current_user.role == "provider":
            if booking.provider_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to reject this booking"
                )
            if current_status != "REQUESTED":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Provider can only reject requests that are currently in REQUESTED status."
                )
        elif current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized"
            )

        # Distinguish cancellation type
        c_type = "PRE_DISPATCH" if current_status in ["REQUESTED", "ACCEPTED"] else "POST_DISPATCH"
        reason_text = payload.cancellation_reason or ("Cancelled by customer" if current_user.role == "customer" else "Rejected by provider")
        booking.cancellation_reason = f"[Type: {c_type}] {reason_text}"

    elif is_customer_accepting_quote:
        pass
    else:
        # Provider advancing status
        if current_user.role != "admin" and booking.provider_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the assigned provider or admin can update the job status"
            )

        valid_next_statuses = ALLOWED_TRANSITIONS.get(current_status, [])
        if target_status not in valid_next_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition from {current_status} to {target_status}. Allowed next status: {valid_next_statuses}"
            )

        if target_status == "ACCEPTED":
            # Check if this was an emergency broadcast booking
            if "[EMERGENCY BROADCAST:" in (booking.problem_description or ""):
                m = re.search(r"\[EMERGENCY BROADCAST:\s*([^\]]+)\]", booking.problem_description)
                if m:
                    eb_ref = m.group(1).strip()
                    other_claimed = db.query(Booking).filter(
                        Booking.id != booking.id,
                        Booking.problem_description.like(f"%[EMERGENCY BROADCAST: {eb_ref}]%"),
                        Booking.status.in_(["ACCEPTED", "ON_THE_WAY", "ARRIVED", "IN_PROGRESS", "COMPLETED"])
                    ).first()
                    if other_claimed:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="This emergency job has already been accepted by another provider."
                        )

                    # Cancel all sibling emergency requests
                    siblings = db.query(Booking).filter(
                        Booking.id != booking.id,
                        Booking.problem_description.like(f"%[EMERGENCY BROADCAST: {eb_ref}]%"),
                        Booking.status == "REQUESTED"
                    ).all()
                    for sib in siblings:
                        sib.status = "CANCELLED"
                        sib.cancellation_reason = f"[Emergency Claimed] Accepted by provider #{booking.provider_id}"
                        add_notification(
                            sib.provider_id,
                            f"Emergency job (Ref: {eb_ref}) has been accepted by another provider and is no longer available.",
                            db
                        )

            is_emergency = "[EMERGENCY BROADCAST:" in (booking.problem_description or "")
            if not is_emergency and check_double_booking(booking.provider_id, booking.scheduled_date, booking.scheduled_time, db, exclude_booking_id=booking.id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot accept: another booking is already confirmed for this provider at this date and time."
                )

    # Perform transition
    booking.status = target_status

    # Handle notifications & side effects per target status
    if target_status == "ACCEPTED":
        cancel_quote_siblings(booking, db)
        add_notification(
            booking.customer_id,
            f"Your booking #{booking.id} for {booking.service.service_name} has been accepted by {booking.provider.name}.",
            db
        )

    elif target_status == "ON_THE_WAY":
        add_notification(
            booking.customer_id,
            f"{booking.provider.name} is on the way to your location for booking #{booking.id}.",
            db
        )

    elif target_status == "ARRIVED":
        add_notification(
            booking.customer_id,
            f"{booking.provider.name} has arrived at your address for booking #{booking.id}.",
            db
        )

    elif target_status == "COMPLETED":
        # HARD RULE: Only approved additional charges enter invoice!
        # Any charge sitting at 'pending' or 'rejected' must NEVER be included in invoice total.
        approved_extra = sum(
            c.amount for c in booking.additional_charges if c.approval_status == "approved"
        )

        labour = round(payload.labour_charge if payload.labour_charge and payload.labour_charge > 0 else booking.price_estimate_min, 2)
        parts = round(payload.parts_charge if payload.parts_charge and payload.parts_charge >= 0 else 0.0, 2)
        service = round(payload.service_charge if payload.service_charge and payload.service_charge >= 0 else 50.0, 2)

        effective_service = round(service + approved_extra, 2)
        subtotal = round(labour + parts + effective_service, 2)
        tax = round(payload.tax if payload.tax is not None else subtotal * 0.18, 2)
        total = round(labour + parts + effective_service + tax, 2)

        booking.final_price = total

        existing_invoice = db.query(Invoice).filter(Invoice.booking_id == booking.id).first()
        if not existing_invoice:
            invoice = Invoice(
                booking_id=booking.id,
                labour_charge=labour,
                parts_charge=parts,
                service_charge=effective_service,
                tax=tax,
                total=total,
                generated_at=datetime.now(timezone.utc)
            )
            db.add(invoice)
        else:
            existing_invoice.labour_charge = labour
            existing_invoice.parts_charge = parts
            existing_invoice.service_charge = effective_service
            existing_invoice.tax = tax
            existing_invoice.total = total

        # Update provider completed jobs
        provider_user = db.query(User).filter(User.id == booking.provider_id).first()
        if provider_user and provider_user.profile:
            provider_user.profile.jobs_completed += 1

        # NOTIFICATION: Service completed -> customer
        add_notification(
            booking.customer_id,
            f"Your service for booking #{booking.id} is completed! Total invoice amount: ₹{total:.2f}. Please leave a review.",
            db
        )

        # RECURRING BOOKINGS: If marked recurring, automatically create exactly ONE next occurrence
        if booking.problem_description and "[Recurring:" in booking.problem_description:
            match = re.search(r"\[Recurring:\s*(weekly|biweekly|monthly)\]", booking.problem_description, re.IGNORECASE)
            if match:
                rec_interval = match.group(1).lower()
                tag_marker = f"[From Recurring Booking #{booking.id}]"
                existing_next = db.query(Booking).filter(
                    Booking.problem_description.like(f"%{tag_marker}%")
                ).first()

                if not existing_next:
                    days_ahead = 7 if rec_interval == "weekly" else (14 if rec_interval == "biweekly" else 28)
                    try:
                        cur_dt = datetime.strptime(booking.scheduled_date, "%Y-%m-%d")
                    except Exception:
                        cur_dt = datetime.now()
                    next_date = (cur_dt + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
                    clean_desc = re.sub(r"\[From Recurring Booking #\d+\]", "", booking.problem_description).strip()
                    next_desc = f"{clean_desc} {tag_marker}"

                    next_booking = Booking(
                        customer_id=booking.customer_id,
                        provider_id=booking.provider_id,
                        category_id=booking.category_id,
                        service_id=booking.service_id,
                        address_id=booking.address_id,
                        problem_description=next_desc,
                        photo_url=booking.photo_url,
                        scheduled_date=next_date,
                        scheduled_time=booking.scheduled_time,
                        status="REQUESTED",
                        price_estimate_min=booking.price_estimate_min,
                        price_estimate_max=booking.price_estimate_max,
                        final_price=None,
                        cancellation_reason=None,
                        created_at=datetime.now(timezone.utc)
                    )
                    db.add(next_booking)
                    db.commit()
                    db.refresh(next_booking)

                    add_notification(
                        booking.customer_id,
                        f"Recurring booking scheduled! Next service on {next_date} at {booking.scheduled_time} (Booking #{next_booking.id}).",
                        db
                    )

    db.commit()
    db.refresh(booking)
    return BookingResponse.model_validate(booking)


# -------------------------------------------------------------
# Live-Feeling Tracking
# -------------------------------------------------------------
@router.put("/{booking_id}/location", response_model=BookingTrackingResponse)
def update_booking_location(
    booking_id: int,
    payload: ProviderLocationUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if current_user.role != "admin" and booking.provider_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the assigned provider can update live location")

    # Update provider coordinates
    if booking.provider and booking.provider.profile:
        booking.provider.profile.latitude = payload.latitude
        booking.provider.profile.longitude = payload.longitude
        db.commit()

    dest_lat = booking.address.latitude if booking.address and booking.address.latitude else 12.9716
    dest_lon = booking.address.longitude if booking.address and booking.address.longitude else 77.5946
    dist_km = round(haversine_distance_km(payload.latitude, payload.longitude, dest_lat, dest_lon), 2)
    eta = max(1, round((dist_km / 25.0) * 60)) if dist_km > 0.05 else 0

    return BookingTrackingResponse(
        booking_id=booking.id,
        status=booking.status,
        provider_name=booking.provider.name if booking.provider else "Provider",
        provider_latitude=payload.latitude,
        provider_longitude=payload.longitude,
        destination_latitude=dest_lat,
        destination_longitude=dest_lon,
        distance_km=dist_km,
        eta_minutes=eta,
        transit_speed_kmh=25.0,
        updated_at=datetime.now(timezone.utc)
    )


@router.get("/{booking_id}/tracking", response_model=BookingTrackingResponse)
def get_booking_tracking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if current_user.role != "admin" and booking.customer_id != current_user.id and booking.provider_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied to tracking")

    prov_lat = booking.provider.profile.latitude if booking.provider and booking.provider.profile and booking.provider.profile.latitude else 12.9350
    prov_lon = booking.provider.profile.longitude if booking.provider and booking.provider.profile and booking.provider.profile.longitude else 77.6150
    dest_lat = booking.address.latitude if booking.address and booking.address.latitude else 12.9716
    dest_lon = booking.address.longitude if booking.address and booking.address.longitude else 77.5946

    dist_km = round(haversine_distance_km(prov_lat, prov_lon, dest_lat, dest_lon), 2)
    eta = max(1, round((dist_km / 25.0) * 60)) if dist_km > 0.05 else 0

    return BookingTrackingResponse(
        booking_id=booking.id,
        status=booking.status,
        provider_name=booking.provider.name if booking.provider else "Provider",
        provider_latitude=prov_lat,
        provider_longitude=prov_lon,
        destination_latitude=dest_lat,
        destination_longitude=dest_lon,
        distance_km=dist_km,
        eta_minutes=eta,
        transit_speed_kmh=25.0,
        updated_at=datetime.now(timezone.utc)
    )


# -------------------------------------------------------------
# In-App Chat
# -------------------------------------------------------------
@router.get("/{booking_id}/messages", response_model=List[ChatMessageResponse])
def get_booking_chat_messages(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # STRICT SERVER-SIDE CHECK: Only customer, assigned provider, or admin
    if current_user.role != "admin" and booking.customer_id != current_user.id and booking.provider_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not authorized to view messages for this booking"
        )

    messages = db.query(ChatMessage).filter(ChatMessage.booking_id == booking_id).order_by(ChatMessage.sent_at.asc()).all()
    results = []
    for m in messages:
        sender = db.query(User).filter(User.id == m.sender_id).first()
        results.append(
            ChatMessageResponse(
                id=m.id,
                booking_id=m.booking_id,
                sender_id=m.sender_id,
                sender_name=sender.name if sender else "User",
                sender_role=sender.role if sender else "user",
                message=m.message,
                sent_at=m.sent_at
            )
        )
    return results


@router.post("/{booking_id}/messages", response_model=ChatMessageResponse)
def send_booking_chat_message(
    booking_id: int,
    payload: ChatMessageCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # STRICT SERVER-SIDE CHECK
    if current_user.role != "admin" and booking.customer_id != current_user.id and booking.provider_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot send messages for this booking"
        )

    msg = ChatMessage(
        booking_id=booking_id,
        sender_id=current_user.id,
        message=payload.message.strip(),
        sent_at=datetime.now(timezone.utc)
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Notify recipient
    recipient_id = booking.customer_id if current_user.id == booking.provider_id else booking.provider_id
    add_notification(
        recipient_id,
        f"Message from {current_user.name} (Booking #{booking.id}): {payload.message[:35]}...",
        db
    )

    return ChatMessageResponse(
        id=msg.id,
        booking_id=msg.booking_id,
        sender_id=msg.sender_id,
        sender_name=current_user.name,
        sender_role=current_user.role,
        message=msg.message,
        sent_at=msg.sent_at
    )


# -------------------------------------------------------------
# Additional-Charge Approval Flow
# -------------------------------------------------------------
@router.post("/{booking_id}/additional-charges", response_model=AdditionalChargeResponse)
def request_additional_charge(
    booking_id: int,
    payload: AdditionalChargeCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if current_user.role != "admin" and booking.provider_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the assigned provider can request additional charges")

    if booking.status in ["COMPLETED", "CANCELLED"]:
        raise HTTPException(status_code=400, detail=f"Cannot add charges to booking in status {booking.status}")

    charge = AdditionalCharge(
        booking_id=booking_id,
        description=payload.description.strip(),
        amount=round(payload.amount, 2),
        approval_status="pending"
    )
    db.add(charge)
    db.commit()
    db.refresh(charge)

    add_notification(
        booking.customer_id,
        f"Provider {booking.provider.name} requested an additional charge of ₹{charge.amount:.2f} for '{charge.description}'. Please review and approve/reject.",
        db
    )

    return AdditionalChargeResponse.model_validate(charge)


@router.get("/{booking_id}/additional-charges", response_model=List[AdditionalChargeResponse])
def get_booking_additional_charges(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if current_user.role != "admin" and booking.customer_id != current_user.id and booking.provider_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    charges = db.query(AdditionalCharge).filter(AdditionalCharge.booking_id == booking_id).all()
    return [AdditionalChargeResponse.model_validate(c) for c in charges]


@router.put("/{booking_id}/additional-charges/{charge_id}", response_model=AdditionalChargeResponse)
def action_additional_charge(
    booking_id: int,
    charge_id: int,
    payload: AdditionalChargeActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if current_user.role != "admin" and booking.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the customer or admin can approve/reject additional charges")

    charge = db.query(AdditionalCharge).filter(
        AdditionalCharge.id == charge_id,
        AdditionalCharge.booking_id == booking_id
    ).first()
    if not charge:
        raise HTTPException(status_code=404, detail="Additional charge not found")

    charge.approval_status = payload.approval_status
    db.commit()
    db.refresh(charge)

    add_notification(
        booking.provider_id,
        f"Customer {booking.customer.name} {payload.approval_status} the additional charge of ₹{charge.amount:.2f} for '{charge.description}'.",
        db
    )

    return AdditionalChargeResponse.model_validate(charge)


# -------------------------------------------------------------
# Complaints & Reviews
# -------------------------------------------------------------
@router.post("/{booking_id}/complaints", response_model=ComplaintResponse)
def file_booking_complaint(
    booking_id: int,
    payload: ComplaintCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if current_user.role != "admin" and booking.customer_id != current_user.id and booking.provider_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only file a complaint for bookings you are part of")

    complaint = Complaint(
        booking_id=booking.id,
        filed_by_user_id=current_user.id,
        reason=payload.reason,
        description=payload.description,
        evidence_photo_url=payload.evidence_photo_url,
        status="open",
        admin_notes=None,
        created_at=datetime.now(timezone.utc)
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)

    add_notification(
        current_user.id,
        f"Complaint filed for booking #{booking.id} (Reason: {payload.reason}). Ticket #{complaint.id}.",
        db
    )

    return ComplaintResponse(
        id=complaint.id,
        booking_id=complaint.booking_id,
        filed_by_user_id=complaint.filed_by_user_id,
        filed_by_name=current_user.name,
        reason=complaint.reason,
        description=complaint.description,
        evidence_photo_url=complaint.evidence_photo_url,
        status=complaint.status,
        admin_notes=complaint.admin_notes,
        created_at=complaint.created_at
    )


@router.get("/{booking_id}/complaints", response_model=List[ComplaintResponse])
def get_booking_complaints(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if current_user.role != "admin" and booking.customer_id != current_user.id and booking.provider_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    complaints = db.query(Complaint).filter(Complaint.booking_id == booking.id).all()
    results = []
    for c in complaints:
        filer = db.query(User).filter(User.id == c.filed_by_user_id).first()
        results.append(
            ComplaintResponse(
                id=c.id,
                booking_id=c.booking_id,
                filed_by_user_id=c.filed_by_user_id,
                filed_by_name=filer.name if filer else "Unknown",
                reason=c.reason,
                description=c.description,
                evidence_photo_url=c.evidence_photo_url,
                status=c.status,
                admin_notes=c.admin_notes,
                created_at=c.created_at
            )
        )
    return results


@router.post("/{booking_id}/review", response_model=ReviewResponse)
def leave_review(
    booking_id: int,
    payload: ReviewCreateRequest,
    current_user: User = Depends(require_role(["customer", "admin"])),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if current_user.role != "admin" and booking.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only review your own bookings")

    if booking.status != "COMPLETED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Reviews can only be submitted for COMPLETED bookings. Current status is {booking.status}.")

    existing_review = db.query(Review).filter(Review.booking_id == booking.id).first()
    if existing_review:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A review has already been submitted for this booking.")

    review = Review(
        booking_id=booking.id,
        customer_id=booking.customer_id,
        provider_id=booking.provider_id,
        rating=payload.rating,
        comment=payload.comment,
        created_at=datetime.now(timezone.utc)
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    all_reviews = db.query(Review).filter(Review.provider_id == booking.provider_id).all()
    if all_reviews:
        new_avg = round(sum(r.rating for r in all_reviews) / len(all_reviews), 2)
        provider_user = db.query(User).filter(User.id == booking.provider_id).first()
        if provider_user and provider_user.profile:
            provider_user.profile.avg_rating = new_avg
            db.commit()

    return ReviewResponse(
        id=review.id,
        booking_id=review.booking_id,
        customer_id=review.customer_id,
        customer_name=current_user.name,
        provider_id=review.provider_id,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at
    )
