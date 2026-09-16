from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, Crop, Scan
from backend.schemas import CropCreate, CropUpdate, CropOut
from backend.auth import get_current_user

router = APIRouter(prefix="/api/crops", tags=["crops"])


@router.get("", response_model=List[CropOut])
def list_crops(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    crops = db.query(Crop).filter(Crop.user_id == user.id).order_by(Crop.created_at.desc()).all()
    results = []
    for c in crops:
        scans_count = db.query(Scan).filter(Scan.crop_id == c.id).count()
        results.append(CropOut(
            id=c.id,
            user_id=c.user_id,
            name=c.name,
            variety=c.variety or "",
            area_acres=c.area_acres or 1.0,
            planting_date=c.planting_date or "",
            location=c.location or "",
            health_status=c.health_status or "Healthy",
            notes=c.notes or "",
            created_at=c.created_at,
            recent_scans_count=scans_count
        ))
    return results


@router.post("", response_model=CropOut, status_code=status.HTTP_201_CREATED)
def create_crop(req: CropCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    crop = Crop(
        user_id=user.id,
        name=req.name.strip(),
        variety=req.variety or "",
        area_acres=req.area_acres or 1.0,
        planting_date=req.planting_date or "",
        location=req.location or "",
        health_status=req.health_status or "Healthy",
        notes=req.notes or "",
        created_at=datetime.now(timezone.utc)
    )
    db.add(crop)
    db.commit()
    db.refresh(crop)
    return CropOut(
        id=crop.id,
        user_id=crop.user_id,
        name=crop.name,
        variety=crop.variety or "",
        area_acres=crop.area_acres or 1.0,
        planting_date=crop.planting_date or "",
        location=crop.location or "",
        health_status=crop.health_status or "Healthy",
        notes=crop.notes or "",
        created_at=crop.created_at,
        recent_scans_count=0
    )


@router.get("/{crop_id}", response_model=CropOut)
def get_crop(crop_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    crop = db.query(Crop).filter(Crop.id == crop_id, Crop.user_id == user.id).first()
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found.")
    scans_count = db.query(Scan).filter(Scan.crop_id == crop.id).count()
    return CropOut(
        id=crop.id,
        user_id=crop.user_id,
        name=crop.name,
        variety=crop.variety or "",
        area_acres=crop.area_acres or 1.0,
        planting_date=crop.planting_date or "",
        location=crop.location or "",
        health_status=crop.health_status or "Healthy",
        notes=crop.notes or "",
        created_at=crop.created_at,
        recent_scans_count=scans_count
    )


@router.put("/{crop_id}", response_model=CropOut)
def update_crop(crop_id: int, req: CropUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    crop = db.query(Crop).filter(Crop.id == crop_id, Crop.user_id == user.id).first()
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found.")

    if req.name is not None:
        crop.name = req.name.strip()
    if req.variety is not None:
        crop.variety = req.variety.strip()
    if req.area_acres is not None:
        crop.area_acres = req.area_acres
    if req.planting_date is not None:
        crop.planting_date = req.planting_date.strip()
    if req.location is not None:
        crop.location = req.location.strip()
    if req.health_status is not None:
        crop.health_status = req.health_status.strip()
    if req.notes is not None:
        crop.notes = req.notes.strip()

    db.commit()
    db.refresh(crop)
    scans_count = db.query(Scan).filter(Scan.crop_id == crop.id).count()
    return CropOut(
        id=crop.id,
        user_id=crop.user_id,
        name=crop.name,
        variety=crop.variety or "",
        area_acres=crop.area_acres or 1.0,
        planting_date=crop.planting_date or "",
        location=crop.location or "",
        health_status=crop.health_status or "Healthy",
        notes=crop.notes or "",
        created_at=crop.created_at,
        recent_scans_count=scans_count
    )


@router.delete("/{crop_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_crop(crop_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    crop = db.query(Crop).filter(Crop.id == crop_id, Crop.user_id == user.id).first()
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found.")
    db.delete(crop)
    db.commit()
    return None
