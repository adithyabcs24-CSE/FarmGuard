import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    User,
    ProviderProfile,
    ProviderService,
    AvailabilitySlot,
    Booking,
    Review,
    ServiceCategory
)
from backend.schemas import (
    ProviderProfileUpdateRequest,
    ProviderProfileResponse,
    ProviderDetailResponse,
    ProviderServiceCreateRequest,
    ProviderServiceResponse,
    AvailabilitySlotCreateRequest,
    AvailabilitySlotResponse,
    BookingDetailResponse,
    InvoiceResponse,
    ReviewResponse,
    MessageResponse,
    ProviderVerificationSubmitRequest
)
from backend.auth import require_role
from backend.utils import get_price_breakdown_note

router = APIRouter(prefix="/api/providers", tags=["providers"])


def format_service(s: ProviderService) -> ProviderServiceResponse:
    res = ProviderServiceResponse.model_validate(s)
    res.price_breakdown_note = get_price_breakdown_note(s.service_name, s.price_min, s.price_max)
    return res


@router.post("/verification/submit", response_model=MessageResponse)
def submit_verification_documents(
    payload: ProviderVerificationSubmitRequest,
    current_user: User = Depends(require_role(["provider"])),
    db: Session = Depends(get_db)
):
    profile = current_user.profile
    if not profile:
        profile = ProviderProfile(user_id=current_user.id)
        db.add(profile)
    profile.verification_documents_json = json.dumps(payload.documents)
    profile.verification_status = "pending"
    db.commit()
    return MessageResponse(message="Verification documents submitted successfully")


@router.get("/profile", response_model=ProviderDetailResponse)
def get_my_provider_profile(
    current_user: User = Depends(require_role(["provider"])),
    db: Session = Depends(get_db)
):
    profile = current_user.profile
    if not profile:
        profile = ProviderProfile(
            user_id=current_user.id,
            bio="Professional local service provider.",
            experience_years=1,
            verification_status="pending",
            service_radius_km=10.0,
            latitude=12.9716,
            longitude=77.5946,
            avg_rating=0.0,
            jobs_completed=0
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

    services = db.query(ProviderService).filter(ProviderService.provider_id == current_user.id).all()
    slots = db.query(AvailabilitySlot).filter(AvailabilitySlot.provider_id == current_user.id).all()
    reviews = db.query(Review).filter(Review.provider_id == current_user.id).order_by(Review.created_at.desc()).all()

    review_responses = []
    for r in reviews:
        cust = db.query(User).filter(User.id == r.customer_id).first()
        review_responses.append(
            ReviewResponse(
                id=r.id,
                booking_id=r.booking_id,
                customer_id=r.customer_id,
                customer_name=cust.name if cust else "Customer",
                provider_id=r.provider_id,
                rating=r.rating,
                comment=r.comment,
                created_at=r.created_at
            )
        )

    return ProviderDetailResponse(
        id=current_user.id,
        profile_id=profile.id,
        name=current_user.name,
        email=current_user.email,
        phone=current_user.phone,
        bio=profile.bio,
        experience_years=profile.experience_years,
        verification_status=profile.verification_status,
        verification_documents_json=profile.verification_documents_json,
        service_radius_km=profile.service_radius_km,
        latitude=profile.latitude,
        longitude=profile.longitude,
        avg_rating=profile.avg_rating,
        jobs_completed=profile.jobs_completed,
        services=[format_service(s) for s in services],
        availability_slots=[AvailabilitySlotResponse.model_validate(s) for s in slots],
        reviews=review_responses
    )


@router.put("/profile", response_model=ProviderProfileResponse)
def update_provider_profile(
    payload: ProviderProfileUpdateRequest,
    current_user: User = Depends(require_role(["provider"])),
    db: Session = Depends(get_db)
):
    profile = current_user.profile
    if not profile:
        profile = ProviderProfile(user_id=current_user.id)
        db.add(profile)

    if payload.bio is not None:
        profile.bio = payload.bio
    if payload.experience_years is not None:
        profile.experience_years = payload.experience_years
    if payload.service_radius_km is not None:
        profile.service_radius_km = payload.service_radius_km
    if payload.latitude is not None:
        profile.latitude = payload.latitude
    if payload.longitude is not None:
        profile.longitude = payload.longitude

    db.commit()
    db.refresh(profile)
    return ProviderProfileResponse.model_validate(profile)


@router.post("/services", response_model=ProviderServiceResponse)
def add_provider_service(
    payload: ProviderServiceCreateRequest,
    current_user: User = Depends(require_role(["provider"])),
    db: Session = Depends(get_db)
):
    # Verify category exists
    cat = db.query(ServiceCategory).filter(ServiceCategory.id == payload.category_id).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service category not found"
        )

    service = ProviderService(
        provider_id=current_user.id,
        category_id=payload.category_id,
        service_name=payload.service_name,
        price_min=payload.price_min,
        price_max=payload.price_max,
        description=payload.description
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return format_service(service)


@router.delete("/services/{service_id}", response_model=MessageResponse)
def delete_provider_service(
    service_id: int,
    current_user: User = Depends(require_role(["provider"])),
    db: Session = Depends(get_db)
):
    service = db.query(ProviderService).filter(
        ProviderService.id == service_id,
        ProviderService.provider_id == current_user.id
    ).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )
    db.delete(service)
    db.commit()
    return MessageResponse(message="Service deleted successfully")


@router.post("/availability", response_model=AvailabilitySlotResponse)
def add_availability_slot(
    payload: AvailabilitySlotCreateRequest,
    current_user: User = Depends(require_role(["provider"])),
    db: Session = Depends(get_db)
):
    slot = AvailabilitySlot(
        provider_id=current_user.id,
        day_of_week=payload.day_of_week,
        start_time=payload.start_time,
        end_time=payload.end_time,
        is_recurring=payload.is_recurring
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return AvailabilitySlotResponse.model_validate(slot)


@router.delete("/availability/{slot_id}", response_model=MessageResponse)
def delete_availability_slot(
    slot_id: int,
    current_user: User = Depends(require_role(["provider"])),
    db: Session = Depends(get_db)
):
    slot = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.id == slot_id,
        AvailabilitySlot.provider_id == current_user.id
    ).first()
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Availability slot not found"
        )
    db.delete(slot)
    db.commit()
    return MessageResponse(message="Availability slot deleted successfully")


@router.get("/jobs", response_model=List[BookingDetailResponse])
def get_provider_jobs(
    current_user: User = Depends(require_role(["provider"])),
    db: Session = Depends(get_db)
):
    bookings = db.query(Booking).filter(
        Booking.provider_id == current_user.id
    ).order_by(Booking.created_at.desc()).all()

    results: List[BookingDetailResponse] = []
    for b in bookings:
        inv = None
        if b.invoice:
            inv = InvoiceResponse.model_validate(b.invoice)

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
                created_at=b.created_at,
                invoice=inv,
                review=rev
            )
        )
    return results
