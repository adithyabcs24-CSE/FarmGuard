from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models import (
    User,
    ProviderProfile,
    ProviderService,
    ServiceCategory,
    Booking,
    Complaint,
    Payment,
    Address,
    Invoice,
    Review
)
from backend.schemas import (
    HealthResponse,
    MessageResponse,
    ProviderSearchItemResponse,
    ProviderServiceResponse,
    ProviderVerificationActionRequest,
    AdminUserResponse,
    UserBlockUpdateRequest,
    CategoryCreateRequest,
    CategoryUpdateRequest,
    CategoryDetailResponse,
    AdminBookingForceCancelRequest,
    AdminComplaintActionRequest,
    PaymentResponse,
    AdminAnalyticsResponse,
    BookingDetailResponse,
    BookingResponse,
    ComplaintResponse,
    InvoiceResponse,
    ReviewResponse,
    AdditionalChargeResponse
)
from backend.auth import require_role
from backend.utils import get_price_breakdown_note, add_notification

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/status", response_model=HealthResponse)
def get_admin_status(current_user: User = Depends(require_role(["admin"]))):
    """Admin service status."""
    return HealthResponse(status="Admin service operational", version="3.0")


# -------------------------------------------------------------
# 1. User Management
# -------------------------------------------------------------
@router.get("/users", response_model=List[AdminUserResponse])
def get_all_users_admin(
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        AdminUserResponse(
            id=u.id,
            role=u.role,
            name=u.name,
            email=u.email,
            phone=u.phone,
            is_blocked=getattr(u, "is_blocked", False),
            created_at=u.created_at
        )
        for u in users
    ]


@router.put("/users/{user_id}/block", response_model=MessageResponse)
def update_user_block_status(
    user_id: int,
    payload: UserBlockUpdateRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin cannot block their own account"
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    target_user.is_blocked = payload.is_blocked
    db.commit()

    action_str = "blocked" if payload.is_blocked else "unblocked"
    msg = f"User {target_user.name} ({target_user.email}) has been {action_str} by admin."
    if payload.admin_notes:
        msg += f" Note: {payload.admin_notes}"

    # If unblocking, notify user
    if not payload.is_blocked:
        add_notification(target_user.id, "Your account has been unblocked by the administrator.", db)

    return MessageResponse(message=msg)


# -------------------------------------------------------------
# 2. Provider Management & Suspension
# -------------------------------------------------------------
@router.get("/providers", response_model=List[ProviderSearchItemResponse])
def get_all_providers_admin(
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    providers = db.query(User).filter(User.role == "provider").all()
    results: List[ProviderSearchItemResponse] = []

    for p in providers:
        profile = p.profile
        if not profile:
            continue

        prov_services = db.query(ProviderService).filter(ProviderService.provider_id == p.id).all()
        service_objs = []
        for s in prov_services:
            svc_res = ProviderServiceResponse.model_validate(s)
            svc_res.price_breakdown_note = get_price_breakdown_note(s.service_name, s.price_min, s.price_max)
            service_objs.append(svc_res)

        results.append(
            ProviderSearchItemResponse(
                id=p.id,
                profile_id=profile.id,
                name=p.name,
                email=p.email,
                phone=p.phone,
                bio=profile.bio,
                experience_years=profile.experience_years,
                verification_status=profile.verification_status,
                verification_documents_json=profile.verification_documents_json,
                service_radius_km=profile.service_radius_km,
                latitude=profile.latitude,
                longitude=profile.longitude,
                avg_rating=profile.avg_rating,
                jobs_completed=profile.jobs_completed,
                distance_km=None,
                services=service_objs
            )
        )

    return results


@router.put("/providers/{provider_id}/verification", response_model=MessageResponse)
def update_provider_verification(
    provider_id: int,
    payload: ProviderVerificationActionRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    provider = db.query(User).filter(User.id == provider_id, User.role == "provider").first()
    if not provider or not provider.profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found"
        )

    provider.profile.verification_status = payload.status
    db.commit()

    # Notify provider of verification outcome
    msg = f"Your provider verification has been {payload.status} by the platform administration."
    if payload.admin_notes:
        msg += f" Note: {payload.admin_notes}"
    add_notification(provider.id, msg, db)

    return MessageResponse(
        message=f"Provider {provider.name} verification status successfully updated to {payload.status}"
    )


@router.put("/providers/{provider_id}/suspend", response_model=MessageResponse)
def suspend_provider(
    provider_id: int,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """
    Suspend provider: forces verification_status back to 'rejected'
    and prevents provider from receiving new bookings.
    """
    provider = db.query(User).filter(User.id == provider_id, User.role == "provider").first()
    if not provider or not provider.profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found"
        )

    provider.profile.verification_status = "rejected"
    db.commit()

    add_notification(
        provider.id,
        "Your provider account has been SUSPENDED by administration. You can no longer accept new service bookings.",
        db
    )

    return MessageResponse(
        message=f"Provider {provider.name} has been suspended and verification revoked."
    )


# -------------------------------------------------------------
# 3. Category Management (CRUD)
# -------------------------------------------------------------
@router.get("/categories", response_model=List[CategoryDetailResponse])
def get_categories_admin(
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    categories = db.query(ServiceCategory).all()
    results = []
    for c in categories:
        svc_count = db.query(ProviderService).filter(ProviderService.category_id == c.id).count()
        results.append(
            CategoryDetailResponse(
                id=c.id,
                name=c.name,
                icon=c.icon,
                description=c.description,
                service_count=svc_count
            )
        )
    return results


@router.post("/categories", response_model=CategoryDetailResponse)
def create_category_admin(
    payload: CategoryCreateRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    existing = db.query(ServiceCategory).filter(
        func.lower(ServiceCategory.name) == payload.name.lower().strip()
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category with this name already exists"
        )

    cat = ServiceCategory(
        name=payload.name.strip(),
        icon=payload.icon.strip(),
        description=payload.description.strip() if payload.description else None
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)

    return CategoryDetailResponse(
        id=cat.id,
        name=cat.name,
        icon=cat.icon,
        description=cat.description,
        service_count=0
    )


@router.put("/categories/{category_id}", response_model=CategoryDetailResponse)
def update_category_admin(
    category_id: int,
    payload: CategoryUpdateRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    cat = db.query(ServiceCategory).filter(ServiceCategory.id == category_id).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    if payload.name:
        dup = db.query(ServiceCategory).filter(
            func.lower(ServiceCategory.name) == payload.name.lower().strip(),
            ServiceCategory.id != category_id
        ).first()
        if dup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another category with this name already exists"
            )
        cat.name = payload.name.strip()

    if payload.icon:
        cat.icon = payload.icon.strip()
    if payload.description is not None:
        cat.description = payload.description.strip()

    db.commit()
    db.refresh(cat)

    svc_count = db.query(ProviderService).filter(ProviderService.category_id == cat.id).count()
    return CategoryDetailResponse(
        id=cat.id,
        name=cat.name,
        icon=cat.icon,
        description=cat.description,
        service_count=svc_count
    )


@router.delete("/categories/{category_id}", response_model=MessageResponse)
def delete_category_admin(
    category_id: int,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    cat = db.query(ServiceCategory).filter(ServiceCategory.id == category_id).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    # Check active bookings
    active_b = db.query(Booking).filter(
        Booking.category_id == category_id,
        Booking.status.in_(["REQUESTED", "ACCEPTED", "ON_THE_WAY", "ARRIVED", "IN_PROGRESS"])
    ).first()
    if active_b:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete category with active service bookings"
        )

    cat_name = cat.name
    # Delete services under category
    db.query(ProviderService).filter(ProviderService.category_id == category_id).delete()
    db.delete(cat)
    db.commit()

    return MessageResponse(message=f"Category '{cat_name}' successfully removed.")


# -------------------------------------------------------------
# 4. Bookings Oversight & Force Cancel
# -------------------------------------------------------------
@router.get("/bookings", response_model=List[BookingDetailResponse])
def get_all_bookings_admin(
    status_filter: Optional[str] = None,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    query = db.query(Booking)
    if status_filter:
        query = query.filter(Booking.status == status_filter.upper())

    bookings = query.order_by(Booking.created_at.desc()).all()
    results = []
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
                customer_name=b.customer.name if b.customer else "Customer",
                customer_phone=b.customer.phone if b.customer else None,
                provider_id=b.provider_id,
                provider_name=b.provider.name if b.provider else "Provider",
                provider_phone=b.provider.phone if b.provider else None,
                category_id=b.category_id,
                category_name=b.category.name if b.category else "Category",
                service_id=b.service_id,
                service_name=b.service.service_name if b.service else "Service",
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


@router.put("/bookings/{booking_id}/cancel", response_model=BookingResponse)
def force_cancel_booking_admin(
    booking_id: int,
    payload: AdminBookingForceCancelRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )

    if booking.status in ["COMPLETED", "CANCELLED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel booking with terminal status {booking.status}"
        )

    # Distinguish cancellation type
    c_type = "PRE_DISPATCH" if booking.status in ["REQUESTED", "ACCEPTED"] else "POST_DISPATCH"
    full_reason = f"[Admin Force-Cancel | Type: {c_type}] {payload.reason}"

    booking.status = "CANCELLED"
    booking.cancellation_reason = full_reason
    db.commit()
    db.refresh(booking)

    # Notify both customer and provider
    add_notification(
        booking.customer_id,
        f"Your booking #{booking.id} was cancelled by administrator. Reason: {payload.reason}",
        db
    )
    add_notification(
        booking.provider_id,
        f"Booking #{booking.id} was cancelled by administrator. Reason: {payload.reason}",
        db
    )

    return BookingResponse.model_validate(booking)


# -------------------------------------------------------------
# 5. Complaints Management
# -------------------------------------------------------------
@router.put("/complaints/{complaint_id}/action", response_model=ComplaintResponse)
def resolve_complaint_admin(
    complaint_id: int,
    payload: AdminComplaintActionRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint ticket not found"
        )

    complaint.status = payload.status
    complaint.admin_notes = payload.admin_notes
    db.commit()
    db.refresh(complaint)

    # Notify filer
    add_notification(
        complaint.filed_by_user_id,
        f"Update on Complaint #{complaint.id} (Booking #{complaint.booking_id}): Status marked as '{payload.status}'. Note: {payload.admin_notes}",
        db
    )

    filer = db.query(User).filter(User.id == complaint.filed_by_user_id).first()
    return ComplaintResponse(
        id=complaint.id,
        booking_id=complaint.booking_id,
        filed_by_user_id=complaint.filed_by_user_id,
        filed_by_name=filer.name if filer else "User",
        reason=complaint.reason,
        description=complaint.description,
        evidence_photo_url=complaint.evidence_photo_url,
        status=complaint.status,
        admin_notes=complaint.admin_notes,
        created_at=complaint.created_at
    )


# -------------------------------------------------------------
# 6. Payments Ledger (Read-Only)
# -------------------------------------------------------------
@router.get("/payments", response_model=List[PaymentResponse])
def get_all_payments_admin(
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    payments = db.query(Payment).order_by(Payment.id.desc()).all()
    if not payments:
        # Generate read-only view from completed invoices if payments table empty
        invoices = db.query(Invoice).all()
        results = []
        for inv in invoices:
            results.append(
                PaymentResponse(
                    id=inv.id,
                    booking_id=inv.booking_id,
                    amount=inv.total,
                    method="upi",
                    status="paid",
                    mock_transaction_id=f"TXN-UPI-{inv.booking_id:04d}-{inv.id:04d}",
                    paid_at=inv.generated_at
                )
            )
        return results

    return [PaymentResponse.model_validate(p) for p in payments]


# -------------------------------------------------------------
# 7. Basic Live Analytics
# -------------------------------------------------------------
@router.get("/analytics", response_model=AdminAnalyticsResponse)
def get_admin_analytics(
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    total_bookings = db.query(Booking).count()
    completed_bookings = db.query(Booking).filter(Booking.status == "COMPLETED").count()
    cancelled_bookings = db.query(Booking).filter(Booking.status == "CANCELLED").count()

    cancellation_rate = round(
        (cancelled_bookings / total_bookings * 100.0) if total_bookings > 0 else 0.0, 1
    )

    # Most requested category
    most_req_cat_row = db.query(
        ServiceCategory.name, func.count(Booking.id)
    ).join(
        Booking, Booking.category_id == ServiceCategory.id
    ).group_by(
        ServiceCategory.id
    ).order_by(
        func.count(Booking.id).desc()
    ).first()

    most_requested_category = most_req_cat_row[0] if most_req_cat_row else "None"

    # Average booking value
    avg_price = db.query(func.avg(Booking.final_price)).filter(
        Booking.status == "COMPLETED",
        Booking.final_price.isnot(None)
    ).scalar()
    avg_booking_value = round(avg_price or 0.0, 2)

    # Most active service area
    active_area_row = db.query(
        Address.label, func.count(Booking.id)
    ).join(
        Booking, Booking.address_id == Address.id
    ).group_by(
        Address.label
    ).order_by(
        func.count(Booking.id).desc()
    ).first()

    most_active_service_area = active_area_row[0] if active_area_row else "None"

    # Total revenue
    total_rev = db.query(func.sum(Booking.final_price)).filter(
        Booking.status == "COMPLETED",
        Booking.final_price.isnot(None)
    ).scalar()
    total_revenue = round(total_rev or 0.0, 2)

    return AdminAnalyticsResponse(
        total_bookings=total_bookings,
        completed_bookings=completed_bookings,
        cancelled_bookings=cancelled_bookings,
        cancellation_rate_percent=cancellation_rate,
        most_requested_category=most_requested_category,
        avg_booking_value=avg_booking_value,
        most_active_service_area=most_active_service_area,
        total_revenue=total_revenue
    )
