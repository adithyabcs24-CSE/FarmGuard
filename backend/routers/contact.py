from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import ContactMessage
from backend.schemas import ContactCreate, ContactOut

router = APIRouter(prefix="/api/contact", tags=["contact"])


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def submit_contact(req: ContactCreate, db: Session = Depends(get_db)):
    msg = ContactMessage(
        name=req.name.strip(),
        email=req.email.lower().strip(),
        subject=req.subject.strip() if req.subject else "FarmGuard Support Request",
        category=req.category.strip() if req.category else "General Inquiry",
        message=req.message.strip(),
        created_at=datetime.now(timezone.utc)
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return ContactOut(
        id=msg.id,
        status="received",
        message="Thank you for contacting FarmGuard AI. An agronomy specialist will review your inquiry within 24 hours."
    )
