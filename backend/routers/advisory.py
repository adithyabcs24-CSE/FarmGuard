from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.schemas import WeatherAdvisory, UpgradeRequest, UserOut
from backend.auth import get_current_user, get_optional_user, get_plan_limit

router = APIRouter(prefix="", tags=["advisory"])


@router.get("/api/weather/advisory", response_model=WeatherAdvisory)
def get_weather_advisory(user: User = Depends(get_optional_user)):
    location = user.location if user and user.location else "Regional Agricultural Zone"
    
    # Typical agro-climatic profile
    return WeatherAdvisory(
        location=location,
        temperature_c=28.5,
        humidity_pct=82,
        condition="Partly Cloudy with High Morning Humidity",
        disease_risk_level="High Fungal Risk",
        risk_alert="Relative humidity exceeds 80% with warm mornings: heightened spore germination risk for Tomato Early/Late Blight and Rice Blast.",
        recommended_actions=[
            "Conduct early morning field scout on lower canopy leaves for water-soaked spots",
            "Ensure field drainage channels are clear and avoid overhead sprinkler watering",
            "Apply prophylactic protective copper or biological Trichoderma spray before rain forecast",
            "Ensure adequate row spacing to accelerate canopy drying after sunrise"
        ]
    )


@router.post("/api/subscription/upgrade", response_model=UserOut)
def upgrade_subscription(
    req: UpgradeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    valid_plans = ["Free", "Active", "FPO"]
    if req.plan_tier not in valid_plans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan tier. Choose from: {valid_plans}"
        )

    user.plan_tier = req.plan_tier
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


@router.post("/api/subscription/reset-quota", response_model=UserOut)
def reset_quota(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.scans_used_this_month = 0
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
