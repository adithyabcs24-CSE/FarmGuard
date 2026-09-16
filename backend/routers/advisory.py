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
    
    temperature = 28.5
    humidity = 82
    condition = "Partly Cloudy with High Morning Humidity"

    from backend.config import WEATHER_API_KEY
    if WEATHER_API_KEY and not WEATHER_API_KEY.startswith("your_") and len(WEATHER_API_KEY) > 10:
        try:
            import httpx
            city = location.split(",")[0].strip()
            res = httpx.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": WEATHER_API_KEY, "units": "metric"},
                timeout=4.0
            )
            if res.status_code == 200:
                wdata = res.json()
                temperature = float(wdata.get("main", {}).get("temp", temperature))
                humidity = int(wdata.get("main", {}).get("humidity", humidity))
                cond_list = wdata.get("weather", [])
                if cond_list:
                    condition = cond_list[0].get("description", condition).title()
        except Exception as e:
            print(f"Weather API request note: {e}")

    # Dynamically evaluate disease risk based on weather parameters
    if humidity >= 80:
        disease_risk = "High Fungal Risk"
        risk_alert = f"Relative humidity is {humidity}% with warm conditions ({temperature}°C): heightened spore germination risk for Blight, Downy Mildew, and Blast."
    elif humidity >= 65:
        disease_risk = "Moderate Disease Risk"
        risk_alert = f"Humidity is {humidity}% with {temperature}°C: favorable for sucking pests (aphids/whitefly) and early fungal development."
    else:
        disease_risk = "Low Disease Risk"
        risk_alert = f"Dry conditions with humidity at {humidity}%: low fungal pressure, monitor for red spider mites in dry heat."

    return WeatherAdvisory(
        location=location,
        temperature_c=temperature,
        humidity_pct=humidity,
        condition=condition,
        disease_risk_level=disease_risk,
        risk_alert=risk_alert,
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
