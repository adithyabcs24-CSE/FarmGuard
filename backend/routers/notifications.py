from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, Notification
from backend.schemas import (
    NotificationResponse,
    NotificationListResponse,
    NotificationMarkReadRequest,
    MessageResponse
)
from backend.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def get_my_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    notifications = db.query(Notification).filter(
        Notification.user_id == current_user.id
    ).order_by(Notification.created_at.desc()).limit(50).all()

    unread_count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()

    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(n) for n in notifications],
        unread_count=unread_count
    )


@router.put("/read", response_model=MessageResponse)
def mark_notifications_read(
    payload: NotificationMarkReadRequest = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    )
    if payload and payload.notification_ids:
        query = query.filter(Notification.id.in_(payload.notification_ids))

    query.update({Notification.is_read: True}, synchronize_session=False)
    db.commit()

    return MessageResponse(message="Notifications marked as read")
