"""
CATEGORY 1 — Functional End-to-End (E2E) Paths  [API layer]

Critical user journeys exercised through the REST API.
Covers: E2E-02, E2E-06, E2E-07, E2E-08
"""
import pytest
import requests

from conftest import BASE_URL, booking_payload, day, query_one


def test_E2E_02_protected_page_requires_login(anon):
    """E2E-02: Requesting /dashboard without a session redirects to the login page."""
    resp = anon.get(f"{BASE_URL}/dashboard", allow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")


def test_E2E_06_api_create_booking(anon):
    """E2E-06: A valid POST /api/bookings creates a confirmed booking."""
    resp = anon.post(f"{BASE_URL}/api/bookings", json=booking_payload(room_id=1))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is True
    booking = body["data"]
    assert booking["booking_id"] > 0
    assert booking["status"] == "confirmed"
    assert booking["room_id"] == 1
    # 2 nights x room 1 base price 3500 = 7000
    assert float(booking["total_price"]) == 7000.00


def test_E2E_07_checked_in_guests_report(anon, manager, reception):
    """E2E-07: A checked-in booking appears in the checked-in guests report."""
    created = anon.post(f"{BASE_URL}/api/bookings", json=booking_payload(room_id=5)).json()["data"]
    bid = created["booking_id"]

    manager.put(f"{BASE_URL}/api/bookings/{bid}", json={"status": "checked_in"})

    resp = reception.get(f"{BASE_URL}/api/guests/checked-in")
    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert any(r["booking_id"] == bid for r in rows), "checked-in guest missing from report"
    row = [r for r in rows if r["booking_id"] == bid][0]
    assert row["room_number"] == "105"
    assert row["guest_name"] == "Test Guest"


@pytest.mark.demo
def test_E2E_08_account_locks_after_repeated_failed_logins(anon):
    """
    E2E-08: Brute-force protection journey.

    After MAX_FAILED_ATTEMPTS (5) consecutive bad passwords the account should be
    locked out, not simply rejected again.

    KNOWN DEFECT D1 — the lockout helpers exist in app.py but are never called by
    the /login route, so the 6th attempt still returns a plain 401.
    """
    for _ in range(5):
        anon.post(f"{BASE_URL}/login", data={"username": "manager", "password": "wrong"})

    sixth = anon.post(f"{BASE_URL}/login", data={"username": "manager", "password": "wrong"})
    is_locked = sixth.status_code == 423 or "locked" in sixth.text.lower()

    assert is_locked, (
        "Expected the account to be LOCKED after 5 failed attempts, but attempt 6 "
        f"returned HTTP {sixth.status_code} with no lockout message. "
        "Defect D1: lockout helpers are never called by /login."
    )
