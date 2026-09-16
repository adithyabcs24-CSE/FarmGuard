from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    User,
    ProviderProfile,
    ServiceCategory,
    ProviderService,
    AvailabilitySlot,
    Address,
    Review
)
from backend.schemas import (
    ServiceCategoryResponse,
    ProviderSearchItemResponse,
    ProviderDetailResponse,
    ProviderServiceResponse,
    AvailabilitySlotResponse,
    ReviewResponse,
    AddressCreateRequest,
    AddressResponse
)
from backend.auth import get_current_user, require_role
from backend.utils import haversine_distance_km, get_price_breakdown_note

router = APIRouter(prefix="/api/customers", tags=["customers"])


def format_service(s: ProviderService) -> ProviderServiceResponse:
    res = ProviderServiceResponse.model_validate(s)
    res.price_breakdown_note = get_price_breakdown_note(s.service_name, s.price_min, s.price_max)
    return res



@router.get("/categories", response_model=List[ServiceCategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    categories = db.query(ServiceCategory).all()
    return [ServiceCategoryResponse.model_validate(c) for c in categories]


@router.get("/providers", response_model=List[ProviderSearchItemResponse])
def search_providers(
    category_id: Optional[int] = Query(None),
    min_rating: Optional[float] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    customer_lat: Optional[float] = Query(None),
    customer_lon: Optional[float] = Query(None),
    max_distance_km: Optional[float] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(User).filter(User.role == "provider")

    if search:
        search_fmt = f"%{search}%"
        query = query.filter(User.name.ilike(search_fmt))

    providers = query.all()
    results: List[ProviderSearchItemResponse] = []

    for provider in providers:
        profile = provider.profile
        if not profile:
            continue

        # Filter by min_rating
        if min_rating is not None and profile.avg_rating < min_rating:
            continue

        # Get services for this provider
        services_query = db.query(ProviderService).filter(ProviderService.provider_id == provider.id)
        if category_id:
            services_query = services_query.filter(ProviderService.category_id == category_id)

        prov_services = services_query.all()
        # If category_id was specified and provider doesn't offer that category, skip
        if category_id and not prov_services:
            continue

        # Filter by price if requested
        if min_price is not None or max_price is not None:
            matches_price = False
            for s in prov_services:
                low = s.price_min
                high = s.price_max
                if min_price is not None and high < min_price:
                    continue
                if max_price is not None and low > max_price:
                    continue
                matches_price = True
                break
            if not matches_price and (category_id or prov_services):
                continue

        # Calculate distance using real Haversine formula
        distance_km = None
        if customer_lat is not None and customer_lon is not None and profile.latitude is not None and profile.longitude is not None:
            distance_km = haversine_distance_km(
                customer_lat, customer_lon, profile.latitude, profile.longitude
            )
            # Filter by maximum distance if requested
            if max_distance_km is not None and distance_km > max_distance_km:
                continue
            # Also respect the provider's own service radius
            if profile.service_radius_km and distance_km > profile.service_radius_km:
                continue

        service_objs = [
            format_service(s) for s in prov_services
        ]

        results.append(
            ProviderSearchItemResponse(
                id=provider.id,
                profile_id=profile.id,
                name=provider.name,
                email=provider.email,
                phone=provider.phone,
                bio=profile.bio,
                experience_years=profile.experience_years,
                verification_status=profile.verification_status,
                verification_documents_json=profile.verification_documents_json,
                service_radius_km=profile.service_radius_km,
                latitude=profile.latitude,
                longitude=profile.longitude,
                avg_rating=profile.avg_rating,
                jobs_completed=profile.jobs_completed,
                distance_km=distance_km,
                services=service_objs
            )
        )

    # Sort results: if distance is present, sort by distance; else by rating descending
    if customer_lat is not None and customer_lon is not None:
        results.sort(key=lambda p: (p.distance_km if p.distance_km is not None else 999999, -p.avg_rating))
    else:
        results.sort(key=lambda p: -p.avg_rating)

    return results


@router.get("/providers/{provider_id}", response_model=ProviderDetailResponse)
def get_provider_detail(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(User).filter(User.id == provider_id, User.role == "provider").first()
    if not provider or not provider.profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found"
        )

    profile = provider.profile
    services = db.query(ProviderService).filter(ProviderService.provider_id == provider.id).all()
    slots = db.query(AvailabilitySlot).filter(AvailabilitySlot.provider_id == provider.id).all()
    reviews = db.query(Review).filter(Review.provider_id == provider.id).order_by(Review.created_at.desc()).all()

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
        id=provider.id,
        profile_id=profile.id,
        name=provider.name,
        email=provider.email,
        phone=provider.phone,
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


@router.get("/addresses", response_model=List[AddressResponse])
def get_addresses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    addresses = db.query(Address).filter(Address.user_id == current_user.id).all()
    return [AddressResponse.model_validate(a) for a in addresses]


@router.post("/addresses", response_model=AddressResponse)
def create_address(
    payload: AddressCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    address = Address(
        user_id=current_user.id,
        label=payload.label,
        full_address=payload.full_address,
        latitude=payload.latitude,
        longitude=payload.longitude
    )
    db.add(address)
    db.commit()
    db.refresh(address)
    return AddressResponse.model_validate(address)
