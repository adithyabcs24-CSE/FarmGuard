import pytest
from fastapi.testclient import TestClient
import sqlite3
import bcrypt
from datetime import datetime, timezone, timedelta

from backend.main import app
from backend.database import get_db, SessionLocal
from backend.models import (
    User,
    ProviderProfile,
    ServiceCategory,
    ProviderService,
    AvailabilitySlot,
    Address,
    Booking,
    Invoice,
    Review
)
from backend.seed import seed_database
from backend.utils import haversine_distance_km

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    seed_database()


def test_schema_integrity():
    """Verify all 15 tables and exact column names exist."""
    conn = sqlite3.connect("localserve.db")
    cursor = conn.cursor()
    expected_schema = {
        'users': ['id', 'role', 'name', 'email', 'phone', 'password_hash', 'created_at', 'is_blocked'],
        'provider_profiles': ['id', 'user_id', 'bio', 'experience_years', 'verification_status', 'verification_documents_json', 'service_radius_km', 'latitude', 'longitude', 'avg_rating', 'jobs_completed'],
        'service_categories': ['id', 'name', 'icon', 'description'],
        'provider_services': ['id', 'provider_id', 'category_id', 'service_name', 'price_min', 'price_max', 'description'],
        'availability_slots': ['id', 'provider_id', 'day_of_week', 'start_time', 'end_time', 'is_recurring'],
        'addresses': ['id', 'user_id', 'label', 'full_address', 'latitude', 'longitude'],
        'bookings': ['id', 'customer_id', 'provider_id', 'category_id', 'service_id', 'address_id', 'problem_description', 'photo_url', 'scheduled_date', 'scheduled_time', 'status', 'price_estimate_min', 'price_estimate_max', 'final_price', 'cancellation_reason', 'created_at'],
        'additional_charges': ['id', 'booking_id', 'description', 'amount', 'approval_status'],
        'invoices': ['id', 'booking_id', 'labour_charge', 'parts_charge', 'service_charge', 'tax', 'total', 'generated_at'],
        'payments': ['id', 'booking_id', 'amount', 'method', 'status', 'mock_transaction_id', 'paid_at'],
        'reviews': ['id', 'booking_id', 'customer_id', 'provider_id', 'rating', 'comment', 'created_at'],
        'complaints': ['id', 'booking_id', 'filed_by_user_id', 'reason', 'description', 'evidence_photo_url', 'status', 'admin_notes', 'created_at'],
        'chat_messages': ['id', 'booking_id', 'sender_id', 'message', 'sent_at'],
        'notifications': ['id', 'user_id', 'message', 'is_read', 'created_at'],
        'favourites': ['id', 'customer_id', 'provider_id']
    }
    for table, expected_cols in expected_schema.items():
        cursor.execute(f"PRAGMA table_info({table});")
        actual_cols = [row[1] for row in cursor.fetchall()]
        assert set(actual_cols) == set(expected_cols), f"Column mismatch in table {table}"
    conn.close()


def test_password_hashing():
    """Verify that passwords are never stored in plaintext and match bcrypt."""
    db = SessionLocal()
    users = db.query(User).all()
    assert len(users) >= 9  # 1 admin, 2 customers, 6 providers
    for user in users:
        assert user.password_hash != "password123"
        assert user.password_hash != "admin123"
        assert user.password_hash.startswith("$2b$") or user.password_hash.startswith("$2a$")
        assert bcrypt.checkpw("password123".encode('utf-8'), user.password_hash.encode('utf-8')) or \
               bcrypt.checkpw("admin123".encode('utf-8'), user.password_hash.encode('utf-8'))
    db.close()


def test_auth_all_three_roles_login_and_register():
    """Verify customer, provider, and admin can login and register."""
    # 1. Admin login
    res = client.post("/api/auth/login", json={"email": "admin@localserve.com", "password": "admin123"})
    assert res.status_code == 200
    admin_token = res.json()["access_token"]
    assert res.json()["user"]["role"] == "admin"

    # Admin access placeholder
    res = client.get("/api/admin/status", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200

    # 2. Customer login
    res = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "password123"})
    assert res.status_code == 200
    customer_token = res.json()["access_token"]
    assert res.json()["user"]["role"] == "customer"

    # Customer trying admin endpoint should be forbidden
    res = client.get("/api/admin/status", headers={"Authorization": f"Bearer {customer_token}"})
    assert res.status_code == 403

    # 3. Provider login
    res = client.post("/api/auth/login", json={"email": "ramesh.plumber@example.com", "password": "password123"})
    assert res.status_code == 200
    provider_token = res.json()["access_token"]
    assert res.json()["user"]["role"] == "provider"

    # 4. Register new customer
    unique_ts = int(datetime.now().timestamp() * 1000)
    res = client.post("/api/auth/register", json={
        "name": "Test Customer",
        "email": f"testcust_{unique_ts}@example.com",
        "password": "password123",
        "role": "customer",
        "phone": "+919999999999"
    })
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "customer"

    # 5. Register new provider
    res = client.post("/api/auth/register", json={
        "name": "Test Electrician",
        "email": f"testelec_{unique_ts}@example.com",
        "password": "password123",
        "role": "provider",
        "phone": "+919999999998",
        "bio": "Certified electrician with quick service.",
        "experience_years": 3,
        "service_radius_km": 15.0,
        "latitude": 12.95,
        "longitude": 77.65
    })
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "provider"


def test_haversine_distance_search():
    """Verify real haversine distance calculation and filtering."""
    # Distance between Bangalore Indiranagar (12.9784, 77.6408) and Koramangala (12.9345, 77.6264)
    # is approximately 5.1 km
    calculated_dist = haversine_distance_km(12.9784, 77.6408, 12.9345, 77.6264)
    assert 4.5 < calculated_dist < 5.5

    # Test search endpoint with customer coordinates
    res = client.get("/api/customers/providers?customer_lat=12.9784&customer_lon=77.6408")
    assert res.status_code == 200
    providers = res.json()
    assert len(providers) > 0
    # Providers should have distance_km populated
    for p in providers:
        assert p["distance_km"] is not None
        assert p["distance_km"] >= 0

    # Filter with max_distance_km = 6.0
    res = client.get("/api/customers/providers?customer_lat=12.9784&customer_lon=77.6408&max_distance_km=6.0")
    assert res.status_code == 200
    close_providers = res.json()
    for p in close_providers:
        assert p["distance_km"] <= 6.0


def test_booking_workflow_and_status_enforcement():
    """Verify full booking lifecycle, double booking rejection, transition sequence enforcement, and review rule."""
    # 1. Customer login
    c_res = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "password123"})
    customer_token = c_res.json()["access_token"]
    cust_headers = {"Authorization": f"Bearer {customer_token}"}

    # 2. Provider login (Ramesh)
    p_res = client.post("/api/auth/login", json={"email": "ramesh.plumber@example.com", "password": "password123"})
    provider_token = p_res.json()["access_token"]
    prov_headers = {"Authorization": f"Bearer {provider_token}"}
    provider_id = p_res.json()["user"]["id"]

    # Get Ramesh's services and slots
    detail_res = client.get(f"/api/customers/providers/{provider_id}")
    assert detail_res.status_code == 200
    prov_detail = detail_res.json()
    service = prov_detail["services"][0]
    service_id = service["id"]
    category_id = service["category_id"]

    # Select a future Monday (Ramesh is available on Mondays 09:00 - 18:00)
    today = datetime.now(timezone.utc)
    days_ahead = (0 - today.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    days_ahead += 7 * ((int(datetime.now().timestamp() * 1000) % 50) + 1)
    target_date = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    target_time = "11:00"

    # Create Booking
    book_res = client.post("/api/bookings", headers=cust_headers, json={
        "provider_id": provider_id,
        "category_id": category_id,
        "service_id": service_id,
        "new_full_address": "Flat 402, Green Glen Layout, Bellandur",
        "new_latitude": 12.9279,
        "new_longitude": 77.6710,
        "problem_description": "Water leaking from bathroom sink valve",
        "scheduled_date": target_date,
        "scheduled_time": target_time
    })
    assert book_res.status_code == 200, book_res.text
    booking_id = book_res.json()["id"]
    assert book_res.json()["status"] == "REQUESTED"

    # RULE CHECK: Attempting to leave a review before COMPLETED must fail with 400
    rev_res = client.post(f"/api/bookings/{booking_id}/review", headers=cust_headers, json={
        "rating": 5,
        "comment": "Too early to review!"
    })
    assert rev_res.status_code == 400
    assert "COMPLETED" in rev_res.json()["detail"]

    # Advance status: REQUESTED -> ACCEPTED
    acc_res = client.put(f"/api/bookings/{booking_id}/status", headers=prov_headers, json={
        "status": "ACCEPTED"
    })
    assert acc_res.status_code == 200
    assert acc_res.json()["status"] == "ACCEPTED"

    # RULE CHECK: Double booking rejection!
    # Another customer attempts to book the exact same provider on the same date and overlapping time
    c2_res = client.post("/api/auth/login", json={"email": "bob@example.com", "password": "password123"})
    cust2_token = c2_res.json()["access_token"]
    cust2_headers = {"Authorization": f"Bearer {cust2_token}"}

    double_book_res = client.post("/api/bookings", headers=cust2_headers, json={
        "provider_id": provider_id,
        "category_id": category_id,
        "service_id": service_id,
        "new_full_address": "Villa 12, Whitefield",
        "problem_description": "Urgent pipe leak",
        "scheduled_date": target_date,
        "scheduled_time": target_time
    })
    assert double_book_res.status_code == 409
    assert "already booked" in double_book_res.json()["detail"]

    # RULE CHECK: Skip status attempt (e.g. ACCEPTED straight to COMPLETED) must fail with 400
    skip_res = client.put(f"/api/bookings/{booking_id}/status", headers=prov_headers, json={
        "status": "COMPLETED"
    })
    assert skip_res.status_code == 400
    assert "Invalid status transition" in skip_res.json()["detail"]

    # RULE CHECK: Non-assigned user attempting to advance status fails with 403
    unauth_advance = client.put(f"/api/bookings/{booking_id}/status", headers=cust_headers, json={
        "status": "ON_THE_WAY"
    })
    assert unauth_advance.status_code == 403

    # Legitimate sequential transitions:
    # 1. ACCEPTED -> ON_THE_WAY
    res1 = client.put(f"/api/bookings/{booking_id}/status", headers=prov_headers, json={"status": "ON_THE_WAY"})
    assert res1.status_code == 200
    assert res1.json()["status"] == "ON_THE_WAY"

    # Attempt to skip to COMPLETED from ON_THE_WAY should fail
    assert client.put(f"/api/bookings/{booking_id}/status", headers=prov_headers, json={"status": "COMPLETED"}).status_code == 400

    # 2. ON_THE_WAY -> ARRIVED
    res2 = client.put(f"/api/bookings/{booking_id}/status", headers=prov_headers, json={"status": "ARRIVED"})
    assert res2.status_code == 200
    assert res2.json()["status"] == "ARRIVED"

    # 3. ARRIVED -> IN_PROGRESS
    res3 = client.put(f"/api/bookings/{booking_id}/status", headers=prov_headers, json={"status": "IN_PROGRESS"})
    assert res3.status_code == 200
    assert res3.json()["status"] == "IN_PROGRESS"

    # 4. IN_PROGRESS -> COMPLETED with invoice breakdown
    res4 = client.put(f"/api/bookings/{booking_id}/status", headers=prov_headers, json={
        "status": "COMPLETED",
        "labour_charge": 350.0,
        "parts_charge": 100.0,
        "service_charge": 50.0,
        "tax": 90.0
    })
    assert res4.status_code == 200
    assert res4.json()["status"] == "COMPLETED"
    assert res4.json()["final_price"] == 590.0

    # Verify invoice was created in invoices table
    b_detail = client.get(f"/api/bookings/{booking_id}", headers=cust_headers).json()
    assert b_detail["invoice"] is not None
    assert b_detail["invoice"]["total"] == 590.0
    assert b_detail["invoice"]["labour_charge"] == 350.0

    # RULE CHECK: Customer can now leave review on COMPLETED booking
    rev_ok = client.post(f"/api/bookings/{booking_id}/review", headers=cust_headers, json={
        "rating": 5,
        "comment": "Quick service and fixed the leak cleanly!"
    })
    assert rev_ok.status_code == 200
    assert rev_ok.json()["rating"] == 5

    # Second review attempt must fail
    rev_dup = client.post(f"/api/bookings/{booking_id}/review", headers=cust_headers, json={
        "rating": 4,
        "comment": "Duplicate review attempt"
    })
    assert rev_dup.status_code == 400


def test_cancellation_rules():
    """Verify cancellation permissions and constraints."""
    c_res = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "password123"})
    cust_headers = {"Authorization": f"Bearer {c_res.json()['access_token']}"}

    p_res = client.post("/api/auth/login", json={"email": "suresh.electric@example.com", "password": "password123"})
    prov_headers = {"Authorization": f"Bearer {p_res.json()['access_token']}"}
    provider_id = p_res.json()["user"]["id"]

    prov_detail = client.get(f"/api/customers/providers/{provider_id}").json()
    service = prov_detail["services"][0]

    # Future unique date (Suresh is available every day)
    rand_offset = int(datetime.now().timestamp() * 1000) % 1000 + 30
    target_date = (datetime.now(timezone.utc) + timedelta(days=rand_offset)).strftime("%Y-%m-%d")

    # 1. Create booking and customer cancels while REQUESTED -> Should succeed
    res1 = client.post("/api/bookings", headers=cust_headers, json={
        "provider_id": provider_id,
        "category_id": service["category_id"],
        "service_id": service["id"],
        "new_full_address": "Indiranagar, Bangalore",
        "problem_description": "Socket sparking",
        "scheduled_date": target_date,
        "scheduled_time": "14:00"
    })
    assert res1.status_code == 200, res1.text
    b1 = res1.json()

    cancel_res = client.put(f"/api/bookings/{b1['id']}/status", headers=cust_headers, json={"status": "CANCELLED"})
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # 2. Create another booking, advance to ON_THE_WAY, customer cancellation should fail
    res2 = client.post("/api/bookings", headers=cust_headers, json={
        "provider_id": provider_id,
        "category_id": service["category_id"],
        "service_id": service["id"],
        "new_full_address": "Indiranagar, Bangalore",
        "problem_description": "Socket sparking 2",
        "scheduled_date": target_date,
        "scheduled_time": "16:00"
    })
    assert res2.status_code == 200, res2.text
    b2 = res2.json()

    client.put(f"/api/bookings/{b2['id']}/status", headers=prov_headers, json={"status": "ACCEPTED"})
    client.put(f"/api/bookings/{b2['id']}/status", headers=prov_headers, json={"status": "ON_THE_WAY"})

    # Customer tries to cancel now -> Should be rejected with 400
    illegal_cancel = client.put(f"/api/bookings/{b2['id']}/status", headers=cust_headers, json={"status": "CANCELLED"})
    assert illegal_cancel.status_code == 400
    assert "Cannot cancel booking once it is ON_THE_WAY" in illegal_cancel.json()["detail"]


def test_provider_profile_edit_and_catalog():
    """Verify provider profile editing, adding/deleting services, and managing availability slots."""
    p_res = client.post("/api/auth/login", json={"email": "suresh.electric@example.com", "password": "password123"})
    prov_headers = {"Authorization": f"Bearer {p_res.json()['access_token']}"}

    # 1. Update general profile
    up_res = client.put("/api/providers/profile", headers=prov_headers, json={
        "bio": "Updated master electrician bio with high voltage expertise.",
        "experience_years": 9,
        "service_radius_km": 18.5,
        "latitude": 12.9350,
        "longitude": 77.6150
    })
    assert up_res.status_code == 200
    assert up_res.json()["experience_years"] == 9
    assert up_res.json()["service_radius_km"] == 18.5

    # 2. Add new service
    categories = client.get("/api/customers/categories").json()
    cat_id = categories[0]["id"]

    new_svc = client.post("/api/providers/services", headers=prov_headers, json={
        "category_id": cat_id,
        "service_name": "Emergency Inverter Battery Diagnostic",
        "price_min": 499.0,
        "price_max": 1299.0,
        "description": "Thorough test of home inverter backup and acid levels"
    })
    assert new_svc.status_code == 200
    svc_id = new_svc.json()["id"]

    # Delete service
    del_svc = client.delete(f"/api/providers/services/{svc_id}", headers=prov_headers)
    assert del_svc.status_code == 200

    # 3. Add availability slot
    new_slot = client.post("/api/providers/availability", headers=prov_headers, json={
        "day_of_week": "Sunday",
        "start_time": "10:00",
        "end_time": "14:00",
        "is_recurring": True
    })
    assert new_slot.status_code == 200
    slot_id = new_slot.json()["id"]

    # Delete availability slot
    del_slot = client.delete(f"/api/providers/availability/{slot_id}", headers=prov_headers)
    assert del_slot.status_code == 200


def test_static_html_and_assets_served():
    """Verify all requested multi-page site HTML files and shared static CSS/JS assets are served."""
    pages = [
        "/index.html",
        "/login.html",
        "/register.html",
        "/customer_dashboard.html",
        "/provider_profile.html",
        "/booking.html",
        "/my_bookings.html",
        "/provider_dashboard.html",
        "/provider_jobs.html",
        "/provider_profile_edit.html",
        "/static/css/style.css",
        "/static/js/api.js",
        "/static/js/auth.js",
        "/static/js/nav.js"
    ]
    for page in pages:
        res = client.get(page)
        assert res.status_code == 200, f"Failed to serve {page}"

