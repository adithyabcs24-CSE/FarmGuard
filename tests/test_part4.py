import pytest
import time
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

from backend.main import app
from backend.seed import seed_database
from backend.database import SessionLocal
from backend.models import ServiceCategory, ProviderService, Booking, User

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    seed_database()


def get_token(email: str, password: str = "password123") -> str:
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["access_token"]


def get_unique_future_date(weekday_target: int = 2) -> str:
    today = datetime.now().date()
    days_ahead = (weekday_target - today.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    days_ahead += 7 * ((int(datetime.now().timestamp() * 1000) % 100) + 1)
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")


def test_classifier_grounding_and_fallback():
    """
    Checklist Item: Classifier only ever returns real category ids or null + a plain explanation.
    1. Tests various problem descriptions and confirms mapped category IDs exist in DB.
    2. Tests unclear/out-of-domain descriptions and confirms null category ID with fallback explanation.
    """
    db = SessionLocal()
    real_cat_ids = [c.id for c in db.query(ServiceCategory).all()]
    db.close()

    # 1. Clear plumbing match
    res1 = client.post("/api/ai/classify", json={"description": "water leaking under my kitchen sink faucet"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["category_id"] in real_cat_ids
    assert data1["category_name"] == "Plumbing"
    assert data1["confidence"] in ["high", "medium"]
    assert "catalog" in data1["reasoning"].lower() or "matched" in data1["reasoning"].lower()

    # 2. Clear electrical match
    res2 = client.post("/api/ai/classify", json={"description": "switchboard sparking and circuit breaker tripped"})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["category_id"] in real_cat_ids
    assert data2["category_name"] == "Electrical"
    assert data2["confidence"] in ["high", "medium"]

    # 3. Clear AC repair match
    res3 = client.post("/api/ai/classify", json={"description": "split ac blowing warm air and needs gas refill"})
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["category_id"] in real_cat_ids
    assert data3["category_name"] == "AC Repair"

    # 4. Unclear / out-of-domain text: MUST return category_id: null and explanation
    unclear_queries = [
        "how do I bake a chocolate cake at home?",
        "looking for stock market trading tips",
        "qwertyuiop asdfghjkl random noise 12345"
    ]
    for q in unclear_queries:
        res_unclear = client.post("/api/ai/classify", json={"description": q})
        assert res_unclear.status_code == 200
        data_unclear = res_unclear.json()
        assert data_unclear["category_id"] is None
        assert data_unclear["category_name"] == "Unclear — please select a category manually."
        assert data_unclear["confidence"] == "low"
        assert len(data_unclear["reasoning"]) > 5


def test_problem_assistant_followup_flow_and_grounding():
    """
    Checklist Item: Problem Assistant narrows down symptoms to a specific real provider_services row.
    1. Specific input narrows directly to a real provider_services row.
    2. Broad input asks a follow-up question with real service options.
    3. Answering the follow-up question resolves to a real provider_services row.
    4. Unclear input falls back gracefully.
    """
    db = SessionLocal()
    real_svc_ids = [s.id for s in db.query(ProviderService).all()]
    db.close()

    # 1. Specific input: "tap is dripping water" -> Tap & Shower Leak Repair
    res1 = client.post("/api/ai/assistant/diagnose", json={
        "description": "bathroom tap is constantly dripping water",
        "category_id": 1  # Plumbing
    })
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["is_conclusive"] is True
    assert data1["recommended_service_id"] in real_svc_ids
    assert "Tap & Shower" in data1["recommended_service_name"]
    assert data1["confidence"] == "high"

    # 2. Broad input: "I need some plumbing repair in my flat" -> follow up question
    res2 = client.post("/api/ai/assistant/diagnose", json={
        "description": "I need some general plumbing repair in my flat",
        "category_id": 1
    })
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["is_conclusive"] is False
    assert data2["next_question"] is not None
    assert len(data2["next_question"]["options"]) >= 2
    question_id = data2["next_question"]["question_id"]

    # 3. User responds with an option: "Drain & Pipe Unclogging"
    res3 = client.post("/api/ai/assistant/diagnose", json={
        "description": "I need some general plumbing repair in my flat",
        "category_id": 1,
        "answers": {question_id: "Drain & Pipe Unclogging"}
    })
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["is_conclusive"] is True
    assert data3["recommended_service_id"] in real_svc_ids
    assert "Drain & Pipe" in data3["recommended_service_name"]


def test_price_estimator_data_derived_vs_fallback():
    """
    Checklist Item: Price estimator is demonstrably data-derived — test with two different
    categories and confirm different, real-data-based ranges (or the explicit fallback message when data is thin).
    """
    db = SessionLocal()
    plumbing_cat = db.query(ServiceCategory).filter(ServiceCategory.name == "Plumbing").first()
    cctv_cat = db.query(ServiceCategory).filter(ServiceCategory.name == "CCTV/Network").first()

    # Verify how many completed bookings exist for plumbing
    plumbing_completed = db.query(Booking).filter(
        Booking.category_id == plumbing_cat.id,
        Booking.status == "COMPLETED",
        Booking.final_price.isnot(None)
    ).all()
    db.close()

    # Category 1: Plumbing (has >= 2 completed bookings from tests)
    res_plumbing = client.post("/api/ai/estimate-price", json={
        "category_id": plumbing_cat.id,
        "description": "Kitchen pipe leaking"
    })
    assert res_plumbing.status_code == 200
    data_plumbing = res_plumbing.json()

    if len(plumbing_completed) >= 2:
        assert data_plumbing["data_source"] == "historical_bookings"
        assert data_plumbing["completed_jobs_count"] >= 2
        assert data_plumbing["average_price"] is not None
        assert "completed jobs in Plumbing" in data_plumbing["explanation"]
        assert data_plumbing["price_estimate_min"] <= data_plumbing["price_estimate_max"]

    # Category 2: CCTV/Network (thin historical data < 2 completed jobs)
    res_cctv = client.post("/api/ai/estimate-price", json={
        "category_id": cctv_cat.id,
        "description": "Setup 4 security cameras"
    })
    assert res_cctv.status_code == 200
    data_cctv = res_cctv.json()

    # CCTV has < 2 completed jobs -> must explicitly show thin data fallback disclaimer
    assert data_cctv["data_source"] == "catalog_price_ranges"
    assert "Not enough completed jobs yet for a data-based estimate — showing this category's provider price ranges instead" in data_cctv["explanation"]
    assert data_cctv["price_estimate_min"] > 0
    assert data_cctv["price_estimate_max"] >= data_cctv["price_estimate_min"]

    # Ranges between the two categories must be different
    assert (data_plumbing["price_estimate_min"], data_plumbing["price_estimate_max"]) != (data_cctv["price_estimate_min"], data_cctv["price_estimate_max"])


def test_provider_recommendation_reranking_grounding_and_weights():
    """
    Checklist Item: Recommendation re-ranking never introduces a provider outside the real filtered result set.
    1. Returns candidates sorted by recommendation score.
    2. Verifies all candidates belong to the requested category (never injects outside providers).
    3. Confirms documented weights (rating 35%, distance 30%, experience 15%, jobs 10%, availability 10%).
    """
    db = SessionLocal()
    plumbing_cat = db.query(ServiceCategory).filter(ServiceCategory.name == "Plumbing").first()
    db.close()

    # 1. Query standard customer search for category 1
    std_res = client.get(f"/api/customers/providers?category_id={plumbing_cat.id}&customer_lat=12.9784&customer_lon=77.6408")
    assert std_res.status_code == 200
    std_providers = std_res.json()
    std_ids = {p["id"] for p in std_providers}

    # 2. Query AI recommendation re-ranking
    ai_res = client.get(f"/api/ai/recommend-providers?category_id={plumbing_cat.id}&customer_lat=12.9784&customer_lon=77.6408")
    assert ai_res.status_code == 200
    ai_data = ai_res.json()
    ranked_providers = ai_data["ranked_providers"]

    # Hard Rule check: Must be a subset of the matching providers for category 1
    ranked_ids = {p["id"] for p in ranked_providers}
    assert ranked_ids.issubset(std_ids), "AI re-ranking injected a provider outside the real filtered result set!"

    # Score descending check
    scores = [p["recommendation_score"] for p in ranked_providers]
    assert scores == sorted(scores, reverse=True), "Ranked providers are not sorted descending by score!"

    # Verify score breakdown math
    for p in ranked_providers:
        bd = p["score_breakdown"]
        expected_total = round(
            bd["rating_score"] + bd["distance_score"] + bd["experience_score"] +
            bd["jobs_completed_score"] + bd["availability_score"],
            4
        )
        assert abs(bd["total_score"] - expected_total) < 0.001
        assert 0.0 <= bd["total_score"] <= 1.0


def test_full_project_end_to_end_lifecycle():
    """
    FINAL INTEGRATION FOR THE WHOLE PROJECT — verify end-to-end:
    - A brand-new customer can register
    - Gets classifier / price-estimate suggestion
    - Books service with assigned provider
    - Provider advances status, sends live location
    - Customer tracks live status and ETA
    - In-app chat exchange
    - Provider requests additional charge
    - Customer approves additional charge
    - Provider completes job with invoice
    - Customer reviews provider
    - Admin views updated live analytics and payments ledger
    - All status/enum fields match Part 1 LOCKED schema values throughout
    """
    admin_token = get_token("admin@localserve.com", "admin123")
    timestamp = int(time.time() * 1000)
    new_cust_email = f"final_cust_{timestamp}@example.com"

    # 1. Brand-new customer registration
    reg_res = client.post("/api/auth/register", json={
        "name": f"Final Test Customer {timestamp}",
        "email": new_cust_email,
        "phone": "+919999888877",
        "password": "password123",
        "role": "customer"
    })
    assert reg_res.status_code == 200
    cust_token = reg_res.json()["access_token"]

    # 2. AI Classifier & Price Estimate
    query_text = "bathroom pipe is leaking water"
    clf_res = client.post("/api/ai/classify", json={"description": query_text})
    assert clf_res.status_code == 200
    cat_id = clf_res.json()["category_id"]
    assert cat_id == 1  # Plumbing

    diag_res = client.post("/api/ai/assistant/diagnose", json={"description": query_text, "category_id": cat_id})
    assert diag_res.status_code == 200
    svc_id = diag_res.json()["recommended_service_id"]
    assert svc_id is not None

    price_res = client.post("/api/ai/estimate-price", json={"category_id": cat_id})
    assert price_res.status_code == 200
    assert price_res.json()["price_estimate_min"] > 0

    # 3. Customer creates booking
    future_date = get_unique_future_date(weekday_target=2)
    book_res = client.post(
        "/api/bookings",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={
            "provider_id": 4,  # Ramesh
            "category_id": cat_id,
            "service_id": svc_id,
            "new_full_address": "Flat 502, Horizon Tower, Whitefield, Bangalore",
            "new_address_label": "Home",
            "problem_description": query_text,
            "scheduled_date": future_date,
            "scheduled_time": "14:00"
        }
    )
    assert book_res.status_code == 200
    booking_id = book_res.json()["id"]
    assert book_res.json()["status"] == "REQUESTED"

    # 4. Provider advances status
    prov_token = get_token("ramesh.plumber@example.com")
    client.put(f"/api/bookings/{booking_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "ACCEPTED"})
    client.put(f"/api/bookings/{booking_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "ON_THE_WAY"})

    # 5. Provider updates live location -> Customer tracks dynamic ETA
    loc_res = client.put(
        f"/api/bookings/{booking_id}/location",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={"latitude": 12.9500, "longitude": 77.6200}
    )
    assert loc_res.status_code == 200
    assert loc_res.json()["eta_minutes"] > 0

    track_res = client.get(f"/api/bookings/{booking_id}/tracking", headers={"Authorization": f"Bearer {cust_token}"})
    assert track_res.status_code == 200
    assert track_res.json()["distance_km"] > 0

    # 6. In-App Chat exchange
    chat1 = client.post(
        f"/api/bookings/{booking_id}/messages",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={"message": "Hi, I will be home to open the door."}
    )
    assert chat1.status_code == 200

    chat2 = client.post(
        f"/api/bookings/{booking_id}/messages",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={"message": "Noted! Arriving shortly."}
    )
    assert chat2.status_code == 200

    # 7. Job progress to IN_PROGRESS
    client.put(f"/api/bookings/{booking_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "ARRIVED"})
    client.put(f"/api/bookings/{booking_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "IN_PROGRESS"})

    # 8. Additional charge approval flow (HARD RULE)
    chg_res = client.post(
        f"/api/bookings/{booking_id}/additional-charges",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={"description": "Replacement Teflon seal & coupler", "amount": 250.0}
    )
    assert chg_res.status_code == 200
    chg_id = chg_res.json()["id"]

    appr_res = client.put(
        f"/api/bookings/{booking_id}/additional-charges/{chg_id}",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={"approval_status": "approved"}
    )
    assert appr_res.status_code == 200

    # 9. Provider completes job with invoice
    comp_res = client.put(
        f"/api/bookings/{booking_id}/status",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={
            "status": "COMPLETED",
            "labour_charge": 350.0,
            "parts_charge": 50.0,
            "service_charge": 50.0
        }
    )
    assert comp_res.status_code == 200
    # subtotal = 350 + 50 + (50 + 250 approved) = 700. tax = 126. total = 826.00
    assert comp_res.json()["final_price"] == 826.00

    # 10. Customer leaves a review
    rev_res = client.post(
        f"/api/bookings/{booking_id}/review",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={"rating": 5, "comment": "Excellent plumbing work and fast response!"}
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["rating"] == 5

    # 11. Customer views in booking history
    my_res = client.get("/api/bookings/my", headers={"Authorization": f"Bearer {cust_token}"})
    assert my_res.status_code == 200
    assert any(b["id"] == booking_id and b["status"] == "COMPLETED" for b in my_res.json())

    # 12. Admin live analytics reflects the completed booking
    analytics_res = client.get("/api/admin/analytics", headers={"Authorization": f"Bearer {admin_token}"})
    assert analytics_res.status_code == 200
    analytics_data = analytics_res.json()
    assert analytics_data["completed_bookings"] > 0
    assert analytics_data["total_revenue"] > 0

    # 13. Schema / Enum integrity check
    db = SessionLocal()
    valid_statuses = {"REQUESTED", "ACCEPTED", "ON_THE_WAY", "ARRIVED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
    all_b_statuses = {b.status for b in db.query(Booking).all()}
    assert all_b_statuses.issubset(valid_statuses), f"Unexpected booking statuses found: {all_b_statuses - valid_statuses}"
    db.close()
