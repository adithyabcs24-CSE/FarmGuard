from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db
from backend.models import User
from backend.schemas import UserRegister, UserLogin, UserProfileUpdate, UserOut, TokenResponse
from backend.auth import hash_password, verify_password, create_access_token, get_current_user, get_plan_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class DemoLoginRequest(BaseModel):
    role: str = "alice"  # alice, rajesh


@router.post("/register", response_model=TokenResponse)
def register(req: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email.lower().strip()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists."
        )

    user = User(
        name=req.name.strip(),
        email=req.email.lower().strip(),
        phone=req.phone or "",
        location=req.location or "",
        preferred_language=req.preferred_language or "English",
        primary_crop=req.primary_crop or "Tomato",
        plan_tier="Free",
        scans_used_this_month=0,
        password_hash=hash_password(req.password),
        created_at=datetime.now(timezone.utc)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "email": user.email})
    user_out = UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone or "",
        location=user.location or "",
        preferred_language=user.preferred_language or "English",
        primary_crop=user.primary_crop or "Tomato",
        plan_tier=user.plan_tier,
        scans_used_this_month=user.scans_used_this_month,
        scan_limit=get_plan_limit(user.plan_tier),
        created_at=user.created_at
    )
    return TokenResponse(access_token=token, token_type="bearer", user=user_out)


@router.post("/login", response_model=TokenResponse)
def login(req: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower().strip()).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. Please check your credentials."
        )

    token = create_access_token({"sub": str(user.id), "email": user.email})
    user_out = UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone or "",
        location=user.location or "",
        preferred_language=user.preferred_language or "English",
        primary_crop=user.primary_crop or "Tomato",
        plan_tier=user.plan_tier,
        scans_used_this_month=user.scans_used_this_month,
        scan_limit=get_plan_limit(user.plan_tier),
        created_at=user.created_at
    )
    return TokenResponse(access_token=token, token_type="bearer", user=user_out)


@router.post("/demo-login", response_model=TokenResponse)
def demo_login(req: DemoLoginRequest, db: Session = Depends(get_db)):
    email = "alice@farmguard.ai" if req.role.lower() == "alice" else "rajesh@farmguard.ai"
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Create demo user on the fly if not seeded
        name = "Alice Sharma" if req.role.lower() == "alice" else "Rajesh Patel"
        crop = "Tomato" if req.role.lower() == "alice" else "Cotton"
        loc = "Nashik, Maharashtra" if req.role.lower() == "alice" else "Surat, Gujarat"
        user = User(
            name=name,
            email=email,
            phone="+91 98765 43210",
            location=loc,
            preferred_language="English",
            primary_crop=crop,
            plan_tier="Active",
            scans_used_this_month=3,
            password_hash=hash_password("farmguard123"),
            created_at=datetime.now(timezone.utc)
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": str(user.id), "email": user.email})
    user_out = UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone or "",
        location=user.location or "",
        preferred_language=user.preferred_language or "English",
        primary_crop=user.primary_crop or "Tomato",
        plan_tier=user.plan_tier,
        scans_used_this_month=user.scans_used_this_month,
        scan_limit=get_plan_limit(user.plan_tier),
        created_at=user.created_at
    )
    return TokenResponse(access_token=token, token_type="bearer", user=user_out)


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone or "",
        location=user.location or "",
        preferred_language=user.preferred_language or "English",
        primary_crop=user.primary_crop or "Tomato",
        plan_tier=user.plan_tier,
        scans_used_this_month=user.scans_used_this_month,
        scan_limit=get_plan_limit(user.plan_tier),
        created_at=user.created_at
    )


@router.put("/profile", response_model=UserOut)
def update_profile(req: UserProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.name is not None:
        user.name = req.name.strip()
    if req.phone is not None:
        user.phone = req.phone.strip()
    if req.location is not None:
        user.location = req.location.strip()
    if req.preferred_language is not None:
        user.preferred_language = req.preferred_language.strip()
    if req.primary_crop is not None:
        user.primary_crop = req.primary_crop.strip()

    db.commit()
    db.refresh(user)

    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone or "",
        location=user.location or "",
        preferred_language=user.preferred_language or "English",
        primary_crop=user.primary_crop or "Tomato",
        plan_tier=user.plan_tier,
        scans_used_this_month=user.scans_used_this_month,
        scan_limit=get_plan_limit(user.plan_tier),
        created_at=user.created_at
    )
