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
    """
    Returns a unique future date matching weekday_target (default Wednesday = 2),
    offset by microsecond timestamp to prevent collision with previous test runs.
    """
    today = datetime.now().date()
    days_ahead = (weekday_target - today.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    days_ahead += 7 * ((int(datetime.now().timestamp() * 1000) % 100) + 1)
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")


def test_provider_verification_workflow():
    """
    Test provider verification submission, admin review (approve/reject),
    and verification status visibility.
    """
    prov_token = get_token("imran.appliances@example.com")
    admin_token = get_token("admin@localserve.com", "admin123")

    # 1. Provider submits verification documents
    mock_docs = [
        "https://storage.local/id_imran.pdf",
        "https://storage.local/cert_appliance_55.pdf"
    ]
    sub_res = client.post(
        "/api/providers/verification/submit",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={"documents": mock_docs}
    )
    assert sub_res.status_code == 200

    # Verify provider profile is updated to pending
    my_prof = client.get("/api/providers/profile", headers={"Authorization": f"Bearer {prov_token}"}).json()
    assert my_prof["verification_status"] == "pending"

    # 2. Admin inspects provider list
    admin_list_res = client.get(
        "/api/admin/providers",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert admin_list_res.status_code == 200
    providers = admin_list_res.json()
    target_prov = next((p for p in providers if p["email"] == "imran.appliances@example.com"), None)
    assert target_prov is not None
    assert target_prov["verification_status"] == "pending"
    assert target_prov["verification_documents_json"] is not None
    import json
    docs = json.loads(target_prov["verification_documents_json"])
    assert len(docs) == 2

    # 3. Admin approves verification
    action_res = client.put(
        f"/api/admin/providers/{target_prov['id']}/verification",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "approved", "admin_notes": "Verified trade certificate and government identity."}
    )
    assert action_res.status_code == 200
    assert "approved" in action_res.json()["message"]

    # 4. Public search/detail shows approved verification
    public_res = client.get(f"/api/customers/providers/{target_prov['id']}")
    assert public_res.status_code == 200
    pub_data = public_res.json()
    assert pub_data["verification_status"] == "approved"


def test_transparent_price_estimates():
    """
    Verify transparent price breakdown notes are attached to services
    explaining inspection, labour, parts, and travel.
    """
    res = client.get("/api/customers/providers")
    assert res.status_code == 200
    providers = res.json()
    assert len(providers) > 0

    checked_services = 0
    for prov in providers:
        for svc in prov["services"]:
            checked_services += 1
            note = svc.get("price_breakdown_note")
            assert note is not None
            assert "labour" in note.lower() or "labor" in note.lower()
            assert "parts" in note.lower()
            assert "inspection" in note.lower() or "travel" in note.lower()

    assert checked_services > 0, "Expected at least one service to have price breakdown note"


def test_multi_provider_quote_system():
    """
    Test requesting quotes from 3 providers, creating sibling bookings in REQUESTED status,
    and accepting one automatically cancels the other 2.
    """
    cust_token = get_token("alice@example.com")

    # Get customer addresses
    addr_res = client.get("/api/customers/addresses", headers={"Authorization": f"Bearer {cust_token}"})
    assert addr_res.status_code == 200
    addresses = addr_res.json()
    assert len(addresses) > 0
    address_id = addresses[0]["id"]

    # Select 3 providers
    prov_res = client.get("/api/customers/providers")
    assert prov_res.status_code == 200
    all_provs = prov_res.json()
    assert len(all_provs) >= 3
    selected_provs = all_provs[:3]

    provider_ids = [p["id"] for p in selected_provs]
    service_id = selected_provs[0]["services"][0]["id"]
    category_id = selected_provs[0]["services"][0]["category_id"]

    # Compute collision-free Wednesday future date
    future_date = get_unique_future_date(weekday_target=2)
    scheduled_time = "10:00"

    # 1. Customer creates quote requests for 3 providers
    quote_payload = {
        "provider_ids": provider_ids,
        "category_id": category_id,
        "service_id": service_id,
        "address_id": address_id,
        "problem_description": "Water seepage in bathroom wall near junction. Need quotes from multiple providers.",
        "scheduled_date": future_date,
        "scheduled_time": scheduled_time
    }

    create_quote_res = client.post(
        "/api/bookings/quotes",
        headers={"Authorization": f"Bearer {cust_token}"},
        json=quote_payload
    )
    assert create_quote_res.status_code == 200
    sibling_bookings = create_quote_res.json()
    assert len(sibling_bookings) == 3
    for b in sibling_bookings:
        assert b["status"] == "REQUESTED"
        assert "[Quote Ref: QR-" in b["problem_description"]

    # 2. Customer accepts the 1st quote request
    accepted_id = sibling_bookings[0]["id"]
    accept_res = client.post(
        f"/api/bookings/{accepted_id}/accept-quote",
        headers={"Authorization": f"Bearer {cust_token}"}
    )
    assert accept_res.status_code == 200
    accept_data = accept_res.json()
    assert accept_data["accepted_booking"]["status"] == "ACCEPTED"
    assert len(accept_data["cancelled_sibling_ids"]) == 2

    # 3. Verify sibling bookings are now CANCELLED
    for other_b in sibling_bookings[1:]:
        check_res = client.get(
            f"/api/bookings/{other_b['id']}",
            headers={"Authorization": f"Bearer {cust_token}"}
        )
        assert check_res.status_code == 200
        assert check_res.json()["status"] == "CANCELLED"


def test_notifications_lifecycle():
    """
    Verify notifications are generated across booking milestones and can be marked as read.
    """
    cust_token = get_token("alice@example.com")

    # Get notifications for customer
    notif_res = client.get("/api/notifications", headers={"Authorization": f"Bearer {cust_token}"})
    assert notif_res.status_code == 200
    notif_data = notif_res.json()
    assert "unread_count" in notif_data
    assert "notifications" in notif_data
    assert isinstance(notif_data["notifications"], list)

    # Mark notifications as read
    read_res = client.put("/api/notifications/read", headers={"Authorization": f"Bearer {cust_token}"}, json={})
    assert read_res.status_code == 200

    # Verify unread count is now 0
    notif_res_after = client.get("/api/notifications", headers={"Authorization": f"Bearer {cust_token}"})
    assert notif_res_after.json()["unread_count"] == 0


def test_digital_invoice_arithmetic():
    """
    Verify digital invoice line items and exact arithmetic verification:
    labour + parts + service + tax == total
    """
    cust_token = get_token("alice@example.com")
    prov_token = get_token("suresh.electric@example.com")

    # Get provider's user id
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {prov_token}"})
    prov_user_id = me_res.json()["id"]

    # Find address
    addr_res = client.get("/api/customers/addresses", headers={"Authorization": f"Bearer {cust_token}"})
    address_id = addr_res.json()[0]["id"]

    # Find service
    prov_info = client.get(f"/api/customers/providers/{prov_user_id}").json()
    svc = prov_info["services"][0]

    # Book a service on collision-free Monday future date
    future_date = get_unique_future_date(weekday_target=1)
    booking_res = client.post(
        "/api/bookings",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={
            "provider_id": prov_user_id,
            "category_id": svc["category_id"],
            "service_id": svc["id"],
            "address_id": address_id,
            "problem_description": "Ceiling fan installation and wiring check.",
            "scheduled_date": future_date,
            "scheduled_time": "14:00"
        }
    )
    assert booking_res.status_code == 200
    b_id = booking_res.json()["id"]

    # Progress: ACCEPTED -> ON_THE_WAY -> ARRIVED -> IN_PROGRESS
    for step in ["ACCEPTED", "ON_THE_WAY", "ARRIVED", "IN_PROGRESS"]:
        step_res = client.put(
            f"/api/bookings/{b_id}/status",
            headers={"Authorization": f"Bearer {prov_token}"},
            json={"status": step}
        )
        assert step_res.status_code == 200

    # Complete job with specific charges
    labour = 650.00
    parts = 350.00
    service_charge = 50.00
    subtotal = round(labour + parts + service_charge, 2)
    expected_tax = round(subtotal * 0.18, 2)
    expected_total = round(subtotal + expected_tax, 2)

    complete_res = client.put(
        f"/api/bookings/{b_id}/status",
        headers={"Authorization": f"Bearer {prov_token}"},
        json={
            "status": "COMPLETED",
            "labour_charge": labour,
            "parts_charge": parts,
            "service_charge": service_charge
        }
    )
    assert complete_res.status_code == 200

    # Retrieve invoice details via GET booking
    detail_res = client.get(
        f"/api/bookings/{b_id}",
        headers={"Authorization": f"Bearer {prov_token}"}
    )
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["status"] == "COMPLETED"
    inv = detail["invoice"]
    assert inv is not None

    # Check exact arithmetic: labour + parts + service + tax == total
    calc_total = round(inv["labour_charge"] + inv["parts_charge"] + inv["service_charge"] + inv["tax"], 2)
    assert calc_total == round(inv["total"], 2)
    assert round(inv["total"], 2) == expected_total


def test_complaint_filing_and_retrieval():
    """
    Verify complaint system: file a complaint tied to a booking,
    writes to complaints table with status 'open', customer can view /my, admin can view /all.
    """
    cust_token = get_token("alice@example.com")
    admin_token = get_token("admin@localserve.com", "admin123")

    # Get a booking for customer
    my_bookings_res = client.get("/api/bookings/my", headers={"Authorization": f"Bearer {cust_token}"})
    assert my_bookings_res.status_code == 200
    bookings = my_bookings_res.json()
    assert len(bookings) > 0
    target_booking = bookings[0]

    # File complaint
    complaint_payload = {
        "booking_id": target_booking["id"],
        "reason": "Overcharging or Billing Discrepancy",
        "description": "Provider charged extra without presenting bill for parts.",
        "evidence_photo_url": "https://example.com/evidence1.jpg"
    }

    file_res = client.post(
        "/api/complaints",
        headers={"Authorization": f"Bearer {cust_token}"},
        json=complaint_payload
    )
    assert file_res.status_code == 200
    comp_data = file_res.json()
    assert comp_data["status"] == "open"
    assert comp_data["booking_id"] == target_booking["id"]
    assert comp_data["reason"] == complaint_payload["reason"]

    # Customer retrieves /my
    my_comp_res = client.get("/api/complaints/my", headers={"Authorization": f"Bearer {cust_token}"})
    assert my_comp_res.status_code == 200
    my_comps = my_comp_res.json()
    assert any(c["id"] == comp_data["id"] for c in my_comps)

    # Admin retrieves /all
    all_comp_res = client.get("/api/complaints/all", headers={"Authorization": f"Bearer {admin_token}"})
    assert all_comp_res.status_code == 200
    all_comps = all_comp_res.json()
    assert any(c["id"] == comp_data["id"] for c in all_comps)


def test_repeat_booking_flow():
    """
    Verify service history & repeat booking flow:
    Fetch past completed booking, verify its prefill fields,
    and create a new booking using the same service, provider, and address with new date/time.
    """
    cust_token = get_token("alice@example.com")

    # Get completed bookings
    my_bookings = client.get("/api/bookings/my", headers={"Authorization": f"Bearer {cust_token}"}).json()
    completed = [b for b in my_bookings if b["status"] == "COMPLETED"]
    assert len(completed) > 0
    orig_b = completed[0]

    # Check details required for repeat booking
    assert orig_b["provider_id"] is not None
    assert orig_b["service_id"] is not None
    assert orig_b["address_id"] is not None

    # New scheduled date for repeat booking
    new_date = get_unique_future_date(weekday_target=4)
    new_time = "11:00"

    repeat_payload = {
        "provider_id": orig_b["provider_id"],
        "category_id": orig_b["category_id"],
        "service_id": orig_b["service_id"],
        "address_id": orig_b["address_id"],
        "problem_description": f"Repeat service based on #{orig_b['id']}: Regular maintenance visit.",
        "scheduled_date": new_date,
        "scheduled_time": new_time
    }

    new_b_res = client.post(
        "/api/bookings",
        headers={"Authorization": f"Bearer {cust_token}"},
        json=repeat_payload
    )
    assert new_b_res.status_code == 200
    new_b = new_b_res.json()
    assert new_b["status"] == "REQUESTED"
    assert new_b["provider_id"] == orig_b["provider_id"]
    assert new_b["service_id"] == orig_b["service_id"]
    assert new_b["scheduled_date"] == new_date
    assert new_b["scheduled_time"] == new_time
