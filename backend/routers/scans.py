import os
import json
import uuid
import base64
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, Crop, Scan
from backend.schemas import ScanOut, ScanStatusUpdate, ScanNoteCreate, DiagnosisResult, ScanAnalyzeRequest
from backend.auth import get_current_user, get_plan_limit
from backend.config import UPLOAD_DIR
from backend.ai_engine import analyze_crop_image

router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.post("/analyze")
def analyze_scan(
    req: ScanAnalyzeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check monthly quota
    limit = get_plan_limit(user.plan_tier)
    if user.scans_used_this_month >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You have reached your {user.plan_tier} plan limit of {limit} scans this month. Please upgrade your plan to continue scanning."
        )

    # Process image
    image_url = req.sample_image_url or "/static/assets/hero-crop.jpg"
    image_bytes = None

    if req.image_base64:
        try:
            b64data = req.image_base64
            if "," in b64data:
                _, b64data = b64data.split(",", 1)
            image_bytes = base64.b64decode(b64data)
            filename = f"scan_{uuid.uuid4().hex[:12]}.jpg"
            filepath = UPLOAD_DIR / filename
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            image_url = f"/static/uploads/{filename}"
        except Exception as e:
            print("Error decoding base64 image:", e)

    # Run AI Agronomy diagnosis
    diagnosis: DiagnosisResult = analyze_crop_image(
        image_bytes=image_bytes,
        crop_name=req.crop_name,
        plant_part=req.plant_part,
        observations=req.observations,
        language=req.language
    )

    # Link crop if crop_id is provided or find matching crop by name
    target_crop = None
    if req.crop_id:
        target_crop = db.query(Crop).filter(Crop.id == req.crop_id, Crop.user_id == user.id).first()
    if not target_crop:
        target_crop = db.query(Crop).filter(Crop.user_id == user.id, Crop.name.ilike(f"%{req.crop_name}%")).first()

    # Determine initial status & update crop health
    status_label = "Monitoring"
    if diagnosis.severity == "Healthy":
        status_label = "Resolved"
        if target_crop:
            target_crop.health_status = "Healthy"
    elif diagnosis.severity in ["High", "Critical"]:
        status_label = "Attention Required"
        if target_crop:
            target_crop.health_status = "Attention Required"
    else:
        status_label = "Monitoring"
        if target_crop and target_crop.health_status != "Attention Required":
            target_crop.health_status = "Monitoring"

    # Create scan record in database
    scan = Scan(
        user_id=user.id,
        crop_id=target_crop.id if target_crop else None,
        crop_name=diagnosis.crop_name,
        image_url=image_url,
        problem_name=diagnosis.problem_name,
        scientific_name=diagnosis.scientific_name,
        problem_type=diagnosis.problem_type,
        severity=diagnosis.severity,
        confidence_pct=diagnosis.confidence_pct,
        symptoms_json=json.dumps(diagnosis.symptoms),
        immediate_actions_json=json.dumps(diagnosis.immediate_actions),
        organic_remedies_json=json.dumps(diagnosis.organic_remedies),
        chemical_controls_json=json.dumps(diagnosis.chemical_controls),
        prevention_tips_json=json.dumps(diagnosis.prevention_tips),
        status="Monitoring" if diagnosis.severity != "Healthy" else "Resolved",
        notes_json=json.dumps([f"{datetime.now(timezone.utc).strftime('%d %b %Y, %I:%M %p')} — Initial AI scan completed."]),
        created_at=datetime.now(timezone.utc)
    )

    user.scans_used_this_month += 1
    db.add(scan)
    db.commit()
    db.refresh(scan)

    return {
        "scan": ScanOut(
            id=scan.id,
            user_id=scan.user_id,
            crop_id=scan.crop_id,
            crop_name=scan.crop_name,
            image_url=scan.image_url,
            problem_name=scan.problem_name,
            scientific_name=scan.scientific_name,
            problem_type=scan.problem_type,
            severity=scan.severity,
            confidence_pct=scan.confidence_pct,
            symptoms=json.loads(scan.symptoms_json or "[]"),
            immediate_actions=json.loads(scan.immediate_actions_json or "[]"),
            organic_remedies=json.loads(scan.organic_remedies_json or "[]"),
            chemical_controls=json.loads(scan.chemical_controls_json or "[]"),
            prevention_tips=json.loads(scan.prevention_tips_json or "[]"),
            status=scan.status,
            notes=json.loads(scan.notes_json or "[]"),
            created_at=scan.created_at
        ),
        "diagnosis": diagnosis,
        "scans_remaining": max(0, limit - user.scans_used_this_month),
        "plan_tier": user.plan_tier
    }


@router.get("", response_model=List[ScanOut])
def list_scans(
    crop_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Scan).filter(Scan.user_id == user.id)
    if crop_id:
        query = query.filter(Scan.crop_id == crop_id)
    if status_filter:
        query = query.filter(Scan.status == status_filter)

    scans = query.order_by(Scan.created_at.desc()).all()
    results = []
    for s in scans:
        results.append(ScanOut(
            id=s.id,
            user_id=s.user_id,
            crop_id=s.crop_id,
            crop_name=s.crop_name,
            image_url=s.image_url or "/assets/hero-crop.jpg",
            problem_name=s.problem_name,
            scientific_name=s.scientific_name or "",
            problem_type=s.problem_type or "Fungal",
            severity=s.severity or "Medium",
            confidence_pct=s.confidence_pct or 85,
            symptoms=json.loads(s.symptoms_json or "[]"),
            immediate_actions=json.loads(s.immediate_actions_json or "[]"),
            organic_remedies=json.loads(s.organic_remedies_json or "[]"),
            chemical_controls=json.loads(s.chemical_controls_json or "[]"),
            prevention_tips=json.loads(s.prevention_tips_json or "[]"),
            status=s.status or "Monitoring",
            notes=json.loads(s.notes_json or "[]"),
            created_at=s.created_at
        ))
    return results


@router.get("/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(Scan).filter(Scan.id == scan_id, Scan.user_id == user.id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scan record not found.")

    return ScanOut(
        id=s.id,
        user_id=s.user_id,
        crop_id=s.crop_id,
        crop_name=s.crop_name,
        image_url=s.image_url or "/assets/hero-crop.jpg",
        problem_name=s.problem_name,
        scientific_name=s.scientific_name or "",
        problem_type=s.problem_type or "Fungal",
        severity=s.severity or "Medium",
        confidence_pct=s.confidence_pct or 85,
        symptoms=json.loads(s.symptoms_json or "[]"),
        immediate_actions=json.loads(s.immediate_actions_json or "[]"),
        organic_remedies=json.loads(s.organic_remedies_json or "[]"),
        chemical_controls=json.loads(s.chemical_controls_json or "[]"),
        prevention_tips=json.loads(s.prevention_tips_json or "[]"),
        status=s.status or "Monitoring",
        notes=json.loads(s.notes_json or "[]"),
        created_at=s.created_at
    )


@router.put("/{scan_id}/status", response_model=ScanOut)
def update_scan_status(
    scan_id: int,
    req: ScanStatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    s = db.query(Scan).filter(Scan.id == scan_id, Scan.user_id == user.id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scan record not found.")

    valid_statuses = ["Monitoring", "Improving", "Resolved"]
    if req.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    s.status = req.status
    notes = json.loads(s.notes_json or "[]")
    notes.append(f"{datetime.now(timezone.utc).strftime('%d %b %Y, %I:%M %p')} — Status updated to {req.status}.")
    s.notes_json = json.dumps(notes)

    # Update crop health status if applicable
    if s.crop_id:
        crop = db.query(Crop).filter(Crop.id == s.crop_id).first()
        if crop:
            if req.status == "Resolved":
                other_active = db.query(Scan).filter(
                    Scan.crop_id == crop.id,
                    Scan.id != s.id,
                    Scan.status != "Resolved"
                ).count()
                if other_active == 0:
                    crop.health_status = "Healthy"
            elif req.status == "Improving":
                crop.health_status = "Monitoring"

    db.commit()
    db.refresh(s)

    return ScanOut(
        id=s.id,
        user_id=s.user_id,
        crop_id=s.crop_id,
        crop_name=s.crop_name,
        image_url=s.image_url or "/assets/hero-crop.jpg",
        problem_name=s.problem_name,
        scientific_name=s.scientific_name or "",
        problem_type=s.problem_type or "Fungal",
        severity=s.severity or "Medium",
        confidence_pct=s.confidence_pct or 85,
        symptoms=json.loads(s.symptoms_json or "[]"),
        immediate_actions=json.loads(s.immediate_actions_json or "[]"),
        organic_remedies=json.loads(s.organic_remedies_json or "[]"),
        chemical_controls=json.loads(s.chemical_controls_json or "[]"),
        prevention_tips=json.loads(s.prevention_tips_json or "[]"),
        status=s.status,
        notes=json.loads(s.notes_json or "[]"),
        created_at=s.created_at
    )


@router.post("/{scan_id}/notes", response_model=ScanOut)
def add_scan_note(
    scan_id: int,
    req: ScanNoteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    s = db.query(Scan).filter(Scan.id == scan_id, Scan.user_id == user.id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scan record not found.")

    notes = json.loads(s.notes_json or "[]")
    timestamp = datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p")
    notes.append(f"{timestamp} — {req.note.strip()}")
    s.notes_json = json.dumps(notes)

    db.commit()
    db.refresh(s)

    return ScanOut(
        id=s.id,
        user_id=s.user_id,
        crop_id=s.crop_id,
        crop_name=s.crop_name,
        image_url=s.image_url or "/assets/hero-crop.jpg",
        problem_name=s.problem_name,
        scientific_name=s.scientific_name or "",
        problem_type=s.problem_type or "Fungal",
        severity=s.severity or "Medium",
        confidence_pct=s.confidence_pct or 85,
        symptoms=json.loads(s.symptoms_json or "[]"),
        immediate_actions=json.loads(s.immediate_actions_json or "[]"),
        organic_remedies=json.loads(s.organic_remedies_json or "[]"),
        chemical_controls=json.loads(s.chemical_controls_json or "[]"),
        prevention_tips=json.loads(s.prevention_tips_json or "[]"),
        status=s.status,
        notes=json.loads(s.notes_json or "[]"),
        created_at=s.created_at
    )


@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scan(scan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(Scan).filter(Scan.id == scan_id, Scan.user_id == user.id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scan record not found.")
    db.delete(s)
    db.commit()
    return None


@router.get("/{scan_id}/report", response_class=HTMLResponse)
def get_printable_report(scan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(Scan).filter(Scan.id == scan_id, Scan.user_id == user.id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scan record not found.")

    symptoms = json.loads(s.symptoms_json or "[]")
    immediate = json.loads(s.immediate_actions_json or "[]")
    organic = json.loads(s.organic_remedies_json or "[]")
    chemical = json.loads(s.chemical_controls_json or "[]")
    prevention = json.loads(s.prevention_tips_json or "[]")
    notes = json.loads(s.notes_json or "[]")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FarmGuard AI Crop Health Advisory - {s.crop_name}</title>
<style>
  body {{ font-family: 'Segoe UI', Tahoma, sans-serif; line-height: 1.6; color: #1e293b; max-width: 800px; margin: 40px auto; padding: 20px; }}
  .header {{ border-bottom: 3px solid #16a34a; padding-bottom: 15px; margin-bottom: 25px; }}
  .badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 14px; }}
  .badge-danger {{ background: #fee2e2; color: #b91c1c; }}
  .badge-warning {{ background: #fef3c7; color: #b45309; }}
  .badge-success {{ background: #dcfce7; color: #15803d; }}
  h1 {{ margin: 0 0 10px 0; color: #0f172a; }}
  h2 {{ color: #16a34a; margin-top: 25px; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; }}
  ul {{ padding-left: 20px; }}
  li {{ margin-bottom: 8px; }}
  .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-bottom: 20px; }}
  .btn-print {{ background: #16a34a; color: white; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer; }}
  @media print {{ .no-print {{ display: none; }} body {{ margin: 0; padding: 15px; }} }}
</style>
</head>
<body>
<div class="no-print" style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
  <a href="/dashboard" style="color: #16a34a; text-decoration: none; font-weight: 600;">← Back to Dashboard</a>
  <button class="btn-print" onclick="window.print()">🖨️ Print / Save as PDF</button>
</div>

<div class="header">
  <h1>🌱 FarmGuard AI Field Advisory Report</h1>
  <div>Farmer: <strong>{user.name}</strong> | Location: <strong>{user.location or 'Local Farm'}</strong> | Date: <strong>{s.created_at.strftime('%B %d, %Y')}</strong></div>
</div>

<div class="card">
  <h3>Crop Diagnosis: {s.crop_name} — {s.problem_name}</h3>
  <p>Scientific Name: <em>{s.scientific_name or 'N/A'}</em> | Category: <strong>{s.problem_type}</strong> | Confidence: <strong>{s.confidence_pct}%</strong></p>
  <span class="badge {'badge-danger' if s.severity in ['High', 'Critical'] else 'badge-warning' if s.severity == 'Medium' else 'badge-success'}">Severity: {s.severity}</span>
  <span class="badge" style="background: #e0f2fe; color: #0369a1; margin-left: 8px;">Status: {s.status}</span>
</div>

<h2>Identified Symptoms</h2>
<ul>{''.join(f'<li>{sym}</li>' for sym in symptoms)}</ul>

<h2>Immediate Action Steps</h2>
<ul>{''.join(f'<li>{act}</li>' for act in immediate)}</ul>

<h2>Organic & Biological Remedies</h2>
<ul>{''.join(f'<li>{org}</li>' for org in organic)}</ul>

<h2>Recommended Chemical Controls</h2>
<ul>{''.join(f'<li>{chem}</li>' for chem in chemical)}</ul>

<h2>Prevention & Cultural Practices</h2>
<ul>{''.join(f'<li>{prev}</li>' for prev in prevention)}</ul>

<h2>Field Follow-up Notes</h2>
<ul>{''.join(f'<li>{n}</li>' for n in notes)}</ul>

<div style="margin-top: 40px; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; padding-top: 15px;">
  <em>Disclaimer: Recommendations are generated based on agro-climatic image analysis and standard agronomic guidelines. Always observe pre-harvest intervals and consult your local agricultural extension officer for regional spray schedules.</em>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)
