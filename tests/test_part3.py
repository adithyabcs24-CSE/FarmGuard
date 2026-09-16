import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

from backend.main import app
from backend.seed import seed_database

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


def test_admin_user_block_unblock_and_login_gating():
    """
    1. Admin can view users.
    2. Admin can block a user.
    3. Blocked user cannot log in (403 Forbidden).
    4. Blocked user with existing token cannot access protected endpoints (403 Forbidden).
    5. Admin cannot block their own account (400 Bad Request).
    6. Admin can unblock user; user can log in again.
    """
    admin_token = get_token("admin@localserve.com", "admin123")
    cust_email = "bob@example.com"
    cust_token = get_token(cust_email)

    # 1. Admin views all users
    users_res = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert users_res.status_code == 200
    users = users_res.json()
    bob = next((u for u in users if u["email"] == cust_email), None)
    admin_user = next((u for u in users if u["email"] == "admin@localserve.com"), None)
    assert bob is not None
    assert bob["is_blocked"] is False

    # 5. Admin cannot block self
    self_block = client.put(
        f"/api/admin/users/{admin_user['id']}/block",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"is_blocked": True, "admin_notes": "test self block"}
    )
    assert self_block.status_code == 400

    try:
        # 2. Block Bob
        block_res = client.put(
            f"/api/admin/users/{bob['id']}/block",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"is_blocked": True, "admin_notes": "Suspicious activity detected"}
        )
        assert block_res.status_code == 200

        # 3. Blocked user login fails
        login_fail = client.post("/api/auth/login", json={"email": cust_email, "password": "password123"})
        assert login_fail.status_code == 403
        assert "blocked" in login_fail.json()["detail"].lower()

        # 4. Existing token rejected with 403
        me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {cust_token}"})
        assert me_res.status_code == 403
    finally:
        # 6. Unblock user
        unblock_res = client.put(
            f"/api/admin/users/{bob['id']}/block",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"is_blocked": False, "admin_notes": "Account verified and cleared"}
        )
        assert unblock_res.status_code == 200

    # Login succeeds again
    login_ok = client.post("/api/auth/login", json={"email": cust_email, "password": "password123"})
    assert login_ok.status_code == 200


def test_admin_provider_suspension_blocks_new_bookings():
    """
    Provider suspension:
    1. Admin calls PUT /api/admin/providers/{id}/suspend.
    2. Verification status forced to 'rejected'.
    3. Customer attempts to book suspended provider -> rejected with 400.
    4. Admin restores verification -> booking allowed.
    """
    admin_token = get_token("admin@localserve.com", "admin123")
    cust_token = get_token("alice@example.com")
    prov_email = "ramesh.plumber@example.com"

    prov_list = client.get("/api/admin/providers", headers={"Authorization": f"Bearer {admin_token}"}).json()
    ramesh = next(p for p in prov_list if p["email"] == prov_email)

    # 1. Suspend Ramesh
    susp_res = client.put(
        f"/api/admin/providers/{ramesh['id']}/suspend",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert susp_res.status_code == 200

    # 2. Verify verification status is rejected
    prov_profile = client.get(f"/api/customers/providers/{ramesh['id']}", headers={"Authorization": f"Bearer {cust_token}"}).json()
    assert prov_profile["verification_status"] == "rejected"

    # 3. Booking attempt must fail
    svc = prov_profile["services"][0]
    future_date = get_unique_future_date(weekday_target=2)  # Wednesday
    book_fail = client.post(
        "/api/bookings",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={
            "provider_id": ramesh["id"],
            "category_id": svc["category_id"],
            "service_id": svc["id"],
            "address_id": 1,
            "problem_description": "Fix leaking faucet under kitchen sink",
            "scheduled_date": future_date,
            "scheduled_time": "10:00"
        }
    )
    assert book_fail.status_code == 400
    assert "suspended" in book_fail.json()["detail"].lower()

    # 4. Restore provider verification
    restore_res = client.put(
        f"/api/admin/providers/{ramesh['id']}/verification",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "approved", "admin_notes": "Re-verified and cleared"}
    )
    assert restore_res.status_code == 200


def test_admin_category_crud():
    """
    Test Admin category CRUD:
    - Create new category
    - Get categories with service count
    - Update category
    - Delete category
    - Cannot delete category with active bookings
    """
    admin_token = get_token("admin@localserve.com", "admin123")

    # 1. Create
    create_res = client.post(
        "/api/admin/categories",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Smart Automation",
            "icon": "🤖",
            "description": "Smart IoT hubs, video doorbells, smart locks"
        }
    )
    assert create_res.status_code == 200
    new_cat = create_res.json()
    cat_id = new_cat["id"]
    assert new_cat["name"] == "Smart Automation"
    assert new_cat["service_count"] == 0

    # Duplicate name should fail
    dup_res = client.post(
        "/api/admin/categories",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Smart Automation", "icon": "🤖"}
    )
    assert dup_res.status_code == 400

    # 2. Update
    update_res = client.put(
        f"/api/admin/categories/{cat_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Smart Home Automation",
            "icon": "🏠",
            "description": "Updated description"
        }
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Smart Home Automation"
    assert update_res.json()["icon"] == "🏠"

    # 3. Delete
    del_res = client.delete(
        f"/api/admin/categories/{cat_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert del_res.status_code == 200

    # 4. Cannot delete category with active bookings (Category 1: Plumbing)
    del_active_cat = client.delete(
        "/api/admin/categories/1",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert del_active_cat.status_code == 400


def test_admin_booking_oversight_and_force_cancel():
    """
    Admin can search/view all bookings and force-cancel with reason and distinction.
    """
    admin_token = get_token("admin@localserve.com", "admin123")
    cust_token = get_token("alice@example.com")

    # Create a booking with Suresh (ID 5, service ID 4)
    future_date = get_unique_future_date(weekday_target=3)  # Thursday
    b_res = client.post(
        "/api/bookings",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={
            "provider_id": 5,  # Suresh (Electrician)
            "category_id": 2,
            "service_id": 4,
            "address_id": 1,
            "problem_description": "Ceiling fan making strange grinding noise",
            "scheduled_date": future_date,
            "scheduled_time": "11:00"
        }
    )
    assert b_res.status_code == 200
    booking_id = b_res.json()["id"]

    # Admin lists bookings
    admin_bookings = client.get("/api/admin/bookings", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert any(b["id"] == booking_id for b in admin_bookings)

    # Admin force cancels
    cancel_res = client.put(
        f"/api/admin/bookings/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "Customer reported severe conflict of schedule"}
    )
    assert cancel_res.status_code == 200
    cancelled_b = cancel_res.json()
    assert cancelled_b["status"] == "CANCELLED"
    assert "PRE_DISPATCH" in cancelled_b["cancellation_reason"]
    assert "Customer reported severe conflict" in cancelled_b["cancellation_reason"]

    # Attempting to cancel already cancelled booking returns 400
    cancel_again = client.put(
        f"/api/admin/bookings/{booking_id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "Cancel again"}
    )
    assert cancel_again.status_code == 400


def test_admin_complaint_action():
    """
    Admin advances complaint status with notes (investigating, resolved, dismissed).
    """
    admin_token = get_token("admin@localserve.com", "admin123")
    cust_token = get_token("alice@example.com")

    # File complaint on booking 1
    comp_res = client.post(
        "/api/bookings/1/complaints",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={
            "reason": "Overcharging or Billing Discrepancy",
            "description": "Provider added an extra charge for tape that was not discussed beforehand"
        }
    )
    assert comp_res.status_code == 200
    comp_id = comp_res.json()["id"]

    # Admin actions complaint: investigating
    action1 = client.put(
        f"/api/admin/complaints/{comp_id}/action",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "status": "investigating",
            "admin_notes": "Contacting service provider for explanation"
        }
    )
    assert action1.status_code == 200
    assert action1.json()["status"] == "investigating"

    # Admin actions complaint: resolved
    action2 = client.put(
        f"/api/admin/complaints/{comp_id}/action",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "status": "resolved",
            "admin_notes": "Provider agreed to refund ₹100 discrepancy. Issue resolved."
        }
    )
    assert action2.status_code == 200
    assert action2.json()["status"] == "resolved"
    assert "Issue resolved" in action2.json()["admin_notes"]


def test_live_tracking_and_eta():
    """
    Test live tracking endpoint:
    - Provider updates location coordinates
    - Customer polls tracking
    - Dynamic ETA computed from distance at 25 km/h
    """
    prov_token = get_token("ramesh.plumber@example.com")
    cust_token = get_token("alice@example.com")

    # Create and advance booking to ON_THE_WAY
    future_date = get_unique_future_date(weekday_target=2)
    b_res = client.post(
        "/api/bookings",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={
            "provider_id": 4,
            "category_id": 1,
            "service_id": 1,
            "address_id": 1,
            "problem_description": "Testing live tracking coordinates",
            "scheduled_date": future_date,
            "scheduled_time": "14:00"
        }
    )
    assert b_res.status_code == 200
    booking_id = b_res.json()["id"]

    client.put(f"/api/bookings/{booking_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "ACCEPTED"})
    client.put(f"/api/bookings/{booking_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "ON_THE_WAY"})

    # Provider updates location (e.g. Indiranagar to Bellandur)
    loc_res = client.put(
        f"/api/bookings/{booking_id}/location",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={"latitude": 12.9350, "longitude": 77.6150}
    )
    assert loc_res.status_code == 200
    loc_data = loc_res.json()
    assert loc_data["booking_id"] == booking_id
    assert loc_data["distance_km"] > 0
    assert loc_data["eta_minutes"] > 0
    assert loc_data["transit_speed_kmh"] == 25.0

    # Customer polls tracking
    track_res = client.get(
        f"/api/bookings/{booking_id}/tracking",
        headers={"Authorization": f"Bearer {cust_token}"}
    )
    assert track_res.status_code == 200
    track_data = track_res.json()
    assert track_data["distance_km"] == loc_data["distance_km"]
    assert track_data["eta_minutes"] == loc_data["eta_minutes"]

    # Third party (Bob) is forbidden
    other_token = get_token("bob@example.com")
    forbidden_track = client.get(
        f"/api/bookings/{booking_id}/tracking",
        headers={"Authorization": f"Bearer {other_token}"}
    )
    assert forbidden_track.status_code == 403


def test_in_app_chat_authorization_and_messages():
    """
    Test in-app chat:
    - Customer and assigned provider can send/receive messages.
    - Third-party user receives 403 Forbidden.
    - Admin can view thread.
    """
    cust_token = get_token("alice@example.com")
    prov_token = get_token("ramesh.plumber@example.com")
    other_token = get_token("bob@example.com")
    admin_token = get_token("admin@localserve.com", "admin123")

    # Use booking 1 (Alice + Ramesh)
    # 1. Customer sends message
    m1 = client.post(
        "/api/bookings/1/messages",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={"message": "Hello Ramesh, please ring the doorbell when you arrive."}
    )
    assert m1.status_code == 200
    assert m1.json()["message"] == "Hello Ramesh, please ring the doorbell when you arrive."

    # 2. Provider replies
    m2 = client.post(
        "/api/bookings/1/messages",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={"message": "Understood Alice! Bringing necessary pipe fittings."}
    )
    assert m2.status_code == 200

    # 3. Third-party is blocked (403 Forbidden)
    forbidden_post = client.post(
        "/api/bookings/1/messages",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"message": "I should not be able to send this."}
    )
    assert forbidden_post.status_code == 403

    forbidden_get = client.get(
        "/api/bookings/1/messages",
        headers={"Authorization": f"Bearer {other_token}"}
    )
    assert forbidden_get.status_code == 403

    # 4. Admin and participants can view
    cust_msgs = client.get("/api/bookings/1/messages", headers={"Authorization": f"Bearer {cust_token}"})
    assert cust_msgs.status_code == 200
    assert len(cust_msgs.json()) >= 2

    admin_msgs = client.get("/api/bookings/1/messages", headers={"Authorization": f"Bearer {admin_token}"})
    assert admin_msgs.status_code == 200


def test_additional_charge_approval_flow_and_hard_rule():
    """
    HARD RULE VERIFICATION:
    1. Provider submits pending additional charges while IN_PROGRESS.
    2. Customer approves one charge, rejects another.
    3. Pending or rejected charges must NEVER be added to invoice total.
    4. Approved charge MUST be included in final price and invoice.
    """
    cust_token = get_token("alice@example.com")
    prov_token = get_token("ramesh.plumber@example.com")

    # Create booking and advance to IN_PROGRESS
    future_date = get_unique_future_date(weekday_target=2)
    b_res = client.post(
        "/api/bookings",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={
            "provider_id": 4,
            "category_id": 1,
            "service_id": 1,
            "address_id": 1,
            "problem_description": "Replace main water inlet valve",
            "scheduled_date": future_date,
            "scheduled_time": "15:00"
        }
    )
    assert b_res.status_code == 200
    booking_id = b_res.json()["id"]

    client.put(f"/api/bookings/{booking_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "ACCEPTED"})
    client.put(f"/api/bookings/{booking_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "ON_THE_WAY"})
    client.put(f"/api/bookings/{booking_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "ARRIVED"})
    client.put(f"/api/bookings/{booking_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "IN_PROGRESS"})

    # Provider requests 3 charges:
    # C1: Approved (₹300)
    c1_res = client.post(
        f"/api/bookings/{booking_id}/additional-charges",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={"description": "Replacement brass pipe", "amount": 300.0}
    )
    assert c1_res.status_code == 200
    c1_id = c1_res.json()["id"]

    # C2: Rejected (₹150)
    c2_res = client.post(
        f"/api/bookings/{booking_id}/additional-charges",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={"description": "Unjustified convenience surcharge", "amount": 150.0}
    )
    assert c2_res.status_code == 200
    c2_id = c2_res.json()["id"]

    # C3: Still Pending (₹200)
    c3_res = client.post(
        f"/api/bookings/{booking_id}/additional-charges",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={"description": "Unconfirmed replacement filter", "amount": 200.0}
    )
    assert c3_res.status_code == 200
    c3_id = c3_res.json()["id"]

    # Customer acts on charges
    appr_res = client.put(
        f"/api/bookings/{booking_id}/additional-charges/{c1_id}",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={"approval_status": "approved"}
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["approval_status"] == "approved"

    rej_res = client.put(
        f"/api/bookings/{booking_id}/additional-charges/{c2_id}",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={"approval_status": "rejected"}
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["approval_status"] == "rejected"

    # Complete booking:
    # Base: labour = 400, parts = 100, service = 50
    # Approved extra: 300
    # Rejected extra: 150 (MUST NOT BE BILLED!)
    # Pending extra: 200 (MUST NOT BE BILLED!)
    # Subtotal = 400 + 100 + (50 + 300) = 850
    # Tax = 850 * 0.18 = 153
    # Total = 1003.00
    comp_res = client.put(
        f"/api/bookings/{booking_id}/status",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={
            "status": "COMPLETED",
            "labour_charge": 400.0,
            "parts_charge": 100.0,
            "service_charge": 50.0
        }
    )
    assert comp_res.status_code == 200
    completed_b = comp_res.json()
    assert completed_b["final_price"] == 1003.00

    # Verify invoice
    detail = client.get(f"/api/bookings/{booking_id}", headers={"Authorization": f"Bearer {cust_token}"}).json()
    assert detail["invoice"] is not None
    assert detail["invoice"]["service_charge"] == 350.00  # 50 base + 300 approved
    assert detail["invoice"]["total"] == 1003.00


def test_recurring_booking_auto_spawns_one_next_occurrence():
    """
    Test recurring booking:
    - Book marked weekly (+7 days)
    - Upon COMPLETED status, auto-spawns exactly one next occurrence in REQUESTED status.
    """
    cust_token = get_token("alice@example.com")
    prov_token = get_token("ramesh.plumber@example.com")

    future_date = get_unique_future_date(weekday_target=2)
    b_res = client.post(
        "/api/bookings",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={
            "provider_id": 4,
            "category_id": 1,
            "service_id": 1,
            "address_id": 1,
            "problem_description": "Weekly garden sprinkler line inspection",
            "scheduled_date": future_date,
            "scheduled_time": "16:00",
            "recurring_interval": "weekly"
        }
    )
    assert b_res.status_code == 200
    orig_id = b_res.json()["id"]

    # Advance to COMPLETED
    client.put(f"/api/bookings/{orig_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "ACCEPTED"})
    client.put(f"/api/bookings/{orig_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "ON_THE_WAY"})
    client.put(f"/api/bookings/{orig_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "ARRIVED"})
    client.put(f"/api/bookings/{orig_id}/status", headers={"Authorization": f"Bearer {prov_token}"}, json={"status": "IN_PROGRESS"})

    comp_res = client.put(
        f"/api/bookings/{orig_id}/status",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={"status": "COMPLETED", "labour_charge": 350.0}
    )
    assert comp_res.status_code == 200

    # Check that exactly one new booking is spawned
    my_bookings = client.get("/api/bookings/my", headers={"Authorization": f"Bearer {cust_token}"}).json()
    tag_str = f"[From Recurring Booking #{orig_id}]"
    matching = [b for b in my_bookings if tag_str in b["problem_description"]]
    assert len(matching) == 1
    next_b = matching[0]

    assert next_b["status"] == "REQUESTED"
    assert next_b["provider_id"] == 4
    assert next_b["service_id"] == 1

    # Verify scheduled date is +7 days
    orig_dt = datetime.strptime(future_date, "%Y-%m-%d")
    next_dt = datetime.strptime(next_b["scheduled_date"], "%Y-%m-%d")
    assert (next_dt - orig_dt).days == 7


def test_emergency_booking_broadcast_and_first_accept_lock():
    """
    Test emergency booking broadcast:
    1. Customer creates emergency request for Category 1 (Plumbing).
    2. Broadcasts to verified plumbing providers.
    3. First provider accepts -> locks job.
    4. Sibling broadcast bookings automatically cancelled.
    """
    cust_token = get_token("alice@example.com")
    prov1_token = get_token("ramesh.plumber@example.com")

    # Broadcast emergency
    em_res = client.post(
        "/api/bookings/emergency",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={
            "category_id": 1,
            "address_id": 1,
            "problem_description": "Water pipe burst under kitchen sink, flooding floor!"
        }
    )
    assert em_res.status_code == 200
    created_siblings = em_res.json()
    assert len(created_siblings) >= 1
    target_booking = created_siblings[0]
    target_id = target_booking["id"]

    # Provider 1 accepts target booking
    accept_res = client.put(
        f"/api/bookings/{target_id}/status",
        headers={"Authorization": f"Bearer {prov1_token}"},
        json={"status": "ACCEPTED"}
    )
    assert accept_res.status_code == 200
    assert accept_res.json()["status"] == "ACCEPTED"

    # Verify sibling requests are cancelled
    if len(created_siblings) > 1:
        other_sibling_id = created_siblings[1]["id"]
        other_b = client.get(f"/api/bookings/{other_sibling_id}", headers={"Authorization": f"Bearer {cust_token}"}).json()
        assert other_b["status"] == "CANCELLED"
        assert "Emergency job accepted by another provider" in other_b["cancellation_reason"]


def test_admin_analytics_and_payments_ledger():
    """
    Test dynamic admin analytics and payments ledger.
    """
    admin_token = get_token("admin@localserve.com", "admin123")

    # Payments ledger
    pmts_res = client.get("/api/admin/payments", headers={"Authorization": f"Bearer {admin_token}"})
    assert pmts_res.status_code == 200
    assert len(pmts_res.json()) > 0

    # Live analytics
    analytics_res = client.get("/api/admin/analytics", headers={"Authorization": f"Bearer {admin_token}"})
    assert analytics_res.status_code == 200
    data = analytics_res.json()

    assert data["total_bookings"] > 0
    assert data["completed_bookings"] > 0
    assert data["total_revenue"] > 0
    assert data["cancellation_rate_percent"] >= 0.0
    assert data["avg_booking_value"] > 0
    assert data["most_requested_category"] != "None"
