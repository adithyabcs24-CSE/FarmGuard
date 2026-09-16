import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import Base, engine, SessionLocal
from backend.seed import seed_database

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    seed_database()


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "FarmGuard AI"


def test_demo_login_alice():
    res = client.post("/api/auth/demo-login", json={"role": "alice"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["name"] == "Alice Sharma"
    assert data["user"]["primary_crop"] == "Tomato"


def test_demo_login_rajesh():
    res = client.post("/api/auth/demo-login", json={"role": "rajesh"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["name"] == "Rajesh Patel"
    assert data["user"]["primary_crop"] == "Cotton"


def test_register_new_user():
    import uuid
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "name": "Sunita Devi",
        "email": email,
        "password": "securepassword123",
        "phone": "+91 98765 00000",
        "location": "Varanasi, UP",
        "preferred_language": "Hindi",
        "primary_crop": "Rice"
    }
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == email
    assert data["user"]["primary_crop"] == "Rice"
    assert data["user"]["preferred_language"] == "Hindi"


def test_crops_crud():
    # Login as Alice
    auth_res = client.post("/api/auth/demo-login", json={"role": "alice"})
    token = auth_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # List crops
    res = client.get("/api/crops", headers=headers)
    assert res.status_code == 200
    crops = res.json()
    assert len(crops) >= 1
    assert any(c["name"] == "Tomato" for c in crops)

    # Create new crop
    create_payload = {
        "name": "Wheat",
        "variety": "HD-3086",
        "area_acres": 2.5,
        "planting_date": "10 Nov 2026",
        "location": "West Field",
        "health_status": "Healthy",
        "notes": "Zinc applied at basal dose"
    }
    create_res = client.post("/api/crops", json=create_payload, headers=headers)
    assert create_res.status_code == 201
    new_crop = create_res.json()
    assert new_crop["name"] == "Wheat"
    assert new_crop["area_acres"] == 2.5
    crop_id = new_crop["id"]

    # Update crop
    update_res = client.put(f"/api/crops/{crop_id}", json={"health_status": "Monitoring"}, headers=headers)
    assert update_res.status_code == 200
    assert update_res.json()["health_status"] == "Monitoring"

    # Delete crop
    del_res = client.delete(f"/api/crops/{crop_id}", headers=headers)
    assert del_res.status_code == 204


def test_ai_scan_analysis():
    auth_res = client.post("/api/auth/demo-login", json={"role": "alice"})
    token = auth_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Analyze sample image with observations
    data = {
        "crop_name": "Tomato",
        "plant_part": "Leaf",
        "observations": "Concentric rings with yellow halo on lower foliage",
        "language": "English",
        "sample_image_url": "/static/assets/hero-crop.jpg"
    }
    res = client.post("/api/scans/analyze", json=data, headers=headers)
    assert res.status_code == 200
    result = res.json()
    assert "diagnosis" in result
    assert "scan" in result
    diag = result["diagnosis"]
    assert diag["crop_name"] == "Tomato"
    assert diag["problem_name"] == "Early Blight"
    assert diag["confidence_pct"] >= 80
    assert len(diag["symptoms"]) > 0
    assert len(diag["immediate_actions"]) > 0
    assert len(diag["organic_remedies"]) > 0
    assert len(diag["chemical_controls"]) > 0


def test_ai_scan_analysis_live_camera_photo():
    auth_res = client.post("/api/auth/demo-login", json={"role": "alice"})
    token = auth_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Minimal valid 1x1 pixel base64 JPEG simulating HTML5 canvas output from live camera
    fake_canvas_jpeg_base64 = (
        "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP////////////////////////////////"
        "//////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAA"
        "AAAAAAAAAAAAAP/aAAgBAQABPxA="
    )

    data = {
        "crop_name": "Tomato",
        "plant_part": "Leaf",
        "observations": "Brown concentric rings on foliage captured via live camera",
        "language": "English",
        "image_base64": fake_canvas_jpeg_base64
    }
    res = client.post("/api/scans/analyze", json=data, headers=headers)
    assert res.status_code == 200
    result = res.json()
    assert "diagnosis" in result
    assert "scan" in result
    assert "/static/uploads/scan_" in result["scan"]["image_url"]
    assert result["diagnosis"]["problem_name"] == "Early Blight"


def test_scan_notes_and_status():
    auth_res = client.post("/api/auth/demo-login", json={"role": "alice"})
    token = auth_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get scans
    res = client.get("/api/scans", headers=headers)
    assert res.status_code == 200
    scans = res.json()
    assert len(scans) > 0
    scan_id = scans[0]["id"]

    # Add note
    note_res = client.post(
        f"/api/scans/{scan_id}/notes",
        json={"note": "Sprayed Trichoderma viride bio-fungicide @ 5g/L"},
        headers=headers
    )
    assert note_res.status_code == 200
    assert any("Trichoderma" in n for n in note_res.json()["notes"])

    # Update status
    status_res = client.put(
        f"/api/scans/{scan_id}/status",
        json={"status": "Improving"},
        headers=headers
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "Improving"

    # Printable report
    report_res = client.get(f"/api/scans/{scan_id}/report", headers=headers)
    assert report_res.status_code == 200
    assert "FarmGuard AI Field Advisory Report" in report_res.text


def test_disease_encyclopedia():
    # Filter by crop
    res = client.get("/api/diseases?crop=Tomato")
    assert res.status_code == 200
    diseases = res.json()
    assert len(diseases) > 0
    assert any("Early Blight" in d["name"] for d in diseases)

    # Search
    search_res = client.get("/api/diseases?search=armyworm")
    assert search_res.status_code == 200
    results = search_res.json()
    assert any("Fall Armyworm" in d["name"] for d in results)


def test_weather_advisory_and_upgrade():
    auth_res = client.post("/api/auth/demo-login", json={"role": "alice"})
    token = auth_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Weather advisory
    res = client.get("/api/weather/advisory", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["humidity_pct"] > 0
    assert "disease_risk_level" in data

    # Upgrade to FPO
    up_res = client.post("/api/subscription/upgrade", json={"plan_tier": "FPO"}, headers=headers)
    assert up_res.status_code == 200
    assert up_res.json()["plan_tier"] == "FPO"
    assert up_res.json()["scan_limit"] == 200


def test_contact_submission():
    payload = {
        "name": "Kisan Cooperative Leader",
        "email": "coop@example.org",
        "category": "FPO & Enterprise",
        "subject": "Community scouting partnership",
        "message": "We have 150 tomato farmers interested in group scan subscriptions."
    }
    res = client.post("/api/contact", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "received"


def test_voice_assistant_chat_english():
    payload = {
        "message": "My tomato leaves have brown concentric rings on lower leaves",
        "language": "English",
        "crop_context": "Tomato"
    }
    res = client.post("/api/assistant/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert "audio_text" in data
    assert data["language"] == "English"
    assert data["detected_crop"] == "Tomato"
    assert data["detected_problem"] == "Early Blight"
    assert len(data["suggested_actions"]) > 0
    assert len(data["follow_ups"]) > 0


def test_voice_assistant_chat_hindi():
    payload = {
        "message": "टमाटर के पत्तों पर गोल काले धब्बे हैं, क्या दवा छिड़कें?",
        "language": "Hindi"
    }
    res = client.post("/api/assistant/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert "audio_text" in data
    assert data["language"] == "Hindi"
    assert data["detected_crop"] == "Tomato"
    assert "किसान भाई" in data["reply"]
    assert "किसान भाई" in data["audio_text"]
    assert len(data["suggested_actions"]) > 0


def test_voice_assistant_chat_kannada():
    payload = {
        "message": "ಟೊಮೆಟೊ ಎಲೆಗಳ ಮೇಲೆ ಕಂದು ಕಲೆಗಳು ಕಾಣುತ್ತಿವೆ, ಏನು ಮಾಡಬೇಕು?",
        "language": "Kannada"
    }
    res = client.post("/api/assistant/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert "audio_text" in data
    assert data["language"] == "Kannada"
    assert data["detected_crop"] == "Tomato"
    assert "ರೈತ ಮಿತ್ರರೇ" in data["reply"]
    assert "ರೈತ ಮಿತ್ರರೇ" in data["audio_text"]
    assert len(data["suggested_actions"]) > 0
    assert len(data["follow_ups"]) > 0


def test_voice_assistant_quick_prompts():
    res = client.get("/api/assistant/quick-prompts")
    assert res.status_code == 200
    prompts = res.json()
    assert len(prompts) >= 4
    assert any(p["language"] == "Kannada" for p in prompts)
    assert any(p["language"] == "Hindi" for p in prompts)
    assert any(p["language"] == "English" for p in prompts)


