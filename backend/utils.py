import math
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.models import Notification


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on the Earth in kilometers.
    Uses the Haversine formula.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None

    # Radius of earth in kilometers
    r = 6371.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    distance = r * c
    return round(distance, 2)


def get_day_name(date_str: str) -> str:
    """
    Given a date string 'YYYY-MM-DD', returns the weekday name:
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%A")


def get_price_breakdown_note(service_name: str, price_min: float, price_max: float) -> str:
    """
    Returns a transparent breakdown note covering inspection, labour, parts, and travel.
    """
    inspection_fee = 99
    base_labour = int(price_min)
    return (
        f"Breakdown: ₹{inspection_fee} inspection + ₹{base_labour}-₹{int(price_max)} labour "
        f"(zero travel fee, replacement parts billed at cost if needed)"
    )


def add_notification(user_id: int, message: str, db: Session) -> Notification:
    """
    Creates and commits a new notification record for a user.
    """
    notif = Notification(
        user_id=user_id,
        message=message,
        is_read=False,
        created_at=datetime.now(timezone.utc)
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif
