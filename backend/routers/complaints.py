from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.models import User, Booking, Complaint
from backend.schemas import (
    ComplaintCreateRequest,
    ComplaintResponse,
    MessageResponse
)
from backend.auth import get_current_user, require_role
from backend.utils import add_notification

router = APIRouter(prefix="/api/complaints", tags=["complaints"])


class DirectComplaintCreateRequest(BaseModel):
    booking_id: int
    reason: str = Field(..., min_length=2, max_length=150)
    description: str = Field(..., min_length=5)
    evidence_photo_url: Optional[str] = None


@router.post("", response_model=ComplaintResponse)
def file_complaint(
    payload: DirectComplaintCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.query(Booking).filter(Booking.id == payload.booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )

    # Permission check: filer must be the customer, assigned provider, or admin
    if current_user.role != "admin" and booking.customer_id != current_user.id and booking.provider_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only file a complaint for bookings you are part of"
        )

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

    # Add confirmation notification for the filer
    add_notification(
        current_user.id,
        f"Complaint filed for booking #{booking.id} (Reason: {payload.reason}). Reference ticket #{complaint.id}.",
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


@router.get("/my", response_model=List[ComplaintResponse])
def get_my_complaints(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    complaints = db.query(Complaint).filter(
        Complaint.filed_by_user_id == current_user.id
    ).order_by(Complaint.created_at.desc()).all()

    return [
        ComplaintResponse(
            id=c.id,
            booking_id=c.booking_id,
            filed_by_user_id=c.filed_by_user_id,
            filed_by_name=current_user.name,
            reason=c.reason,
            description=c.description,
            evidence_photo_url=c.evidence_photo_url,
            status=c.status,
            admin_notes=c.admin_notes,
            created_at=c.created_at
        )
        for c in complaints
    ]


@router.get("/all", response_model=List[ComplaintResponse])
def get_all_complaints_admin(
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    complaints = db.query(Complaint).order_by(Complaint.created_at.desc()).all()
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
