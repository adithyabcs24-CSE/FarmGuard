import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Disease
from backend.schemas import DiseaseOut

router = APIRouter(prefix="/api/diseases", tags=["diseases"])


@router.get("", response_model=List[DiseaseOut])
def list_diseases(
    crop: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Disease)
    if crop:
        query = query.filter(Disease.crop.ilike(f"%{crop}%"))
    if category:
        query = query.filter(Disease.category.ilike(f"%{category}%"))
    if search:
        s = f"%{search}%"
        query = query.filter((Disease.name.ilike(s)) | (Disease.description.ilike(s)) | (Disease.scientific_name.ilike(s)))

    diseases = query.order_by(Disease.crop.asc(), Disease.name.asc()).all()
    results = []
    for d in diseases:
        results.append(DiseaseOut(
            id=d.id,
            crop=d.crop,
            name=d.name,
            scientific_name=d.scientific_name or "",
            category=d.category or "Fungal",
            severity_level=d.severity_level or "Medium",
            description=d.description or "",
            symptoms=json.loads(d.symptoms_json or "[]"),
            organic_controls=json.loads(d.organic_controls_json or "[]"),
            chemical_controls=json.loads(d.chemical_controls_json or "[]"),
            prevention=json.loads(d.prevention_json or "[]"),
            image_url=d.image_url or "/assets/hero-crop.jpg"
        ))
    return results


@router.get("/{disease_id}", response_model=DiseaseOut)
def get_disease(disease_id: int, db: Session = Depends(get_db)):
    d = db.query(Disease).filter(Disease.id == disease_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Disease entry not found.")
    return DiseaseOut(
        id=d.id,
        crop=d.crop,
        name=d.name,
        scientific_name=d.scientific_name or "",
        category=d.category or "Fungal",
        severity_level=d.severity_level or "Medium",
        description=d.description or "",
        symptoms=json.loads(d.symptoms_json or "[]"),
        organic_controls=json.loads(d.organic_controls_json or "[]"),
        chemical_controls=json.loads(d.chemical_controls_json or "[]"),
        prevention=json.loads(d.prevention_json or "[]"),
        image_url=d.image_url or "/assets/hero-crop.jpg"
    )
