"""
CATEGORY 2 — Boundary & Edge Cases

Field validation, min/max inputs, malformed data and error handling.
Covers: BND-01 .. BND-13
"""
import mysql.connector
import pytest
import requests

from conftest import BASE_URL, booking_payload, day, db_connect, query_one


# ---------------------------------------------------------------- login bounds
def test_BND_01_login_wrong_password(anon):
    """BND-01: Correct username with wrong password is rejected with 401."""
    resp = anon.post(f"{BASE_URL}/login", data={"username": "manager", "password": "wrongpass"})
    assert resp.status_code == 401
    assert "invalid credentials" in resp.text.lower()


def test_BND_02_open_redirect_guard_on_next_param(anon):
    """BND-02: An absolute external URL in ?next= must not be honoured."""
    resp = anon.post(f"{BASE_URL}/login?next=https://evil.example.com",
                     data={"username": "manager", "password": "manager123"},
                     allow_redirects=False)
    assert resp.status_code in (301, 302)
    location = resp.headers.get("Location", "")
    assert "evil.example.com" not in location
    assert "/dashboard" in location


# -------------------------------------------------------------- booking bounds
def test_BND_03_checkout_equals_checkin(anon):
    """BND-03: Zero-night booking (check-out == check-in) is rejected."""
    resp = anon.post(f"{BASE_URL}/api/bookings",
                     json=booking_payload(room_id=1, nights_from=2, nights_to=2))
    assert resp.status_code == 400
    assert "check-out must be after check-in" in resp.json()["error"].lower()


@pytest.mark.demo
def test_BND_04_checkout_before_checkin(anon):
    """BND-04: Negative-night booking (check-out before check-in) is rejected."""
    resp = anon.post(f"{BASE_URL}/api/bookings",
                     json=booking_payload(room_id=1, nights_from=5, nights_to=2))
    assert resp.status_code == 400
    assert "check-out must be after check-in" in resp.json()["error"].lower()


@pytest.mark.demo
def test_BND_05_invalid_date_format(anon):
    """
    BND-05: A malformed date must be rejected with a clean 400 'Invalid date format'.

    KNOWN DEFECT — the availability check parses the dates *before* the guarded
    try/except block, so a bad format raises an uncaught ValueError (HTTP 500).
    """
    resp = anon.post(f"{BASE_URL}/api/bookings",
                     json=booking_payload(room_id=1, check_in="2026/13/40", check_out="2026-12-01"))
    assert resp.status_code == 400, (
        f"Expected 400 for a malformed date, got {resp.status_code} "
        "(unhandled ValueError leaks a 500)."
    )
    assert "invalid date format" in resp.json()["error"].lower()


def test_BND_06_missing_required_field(anon):
    """BND-06: Omitting a required field is rejected with 400."""
    payload = booking_payload(room_id=1)
    del payload["guest_email"]
    resp = anon.post(f"{BASE_URL}/api/bookings", json=payload)
    assert resp.status_code == 400
    assert "missing required fields" in resp.json()["error"].lower()


def test_BND_07_nonexistent_room(anon):
    """BND-07: Booking a room id that does not exist returns 404."""
    resp = anon.post(f"{BASE_URL}/api/bookings", json=booking_payload(room_id=9999))
    assert resp.status_code == 404
    assert "room not found" in resp.json()["error"].lower()


@pytest.mark.demo
def test_BND_08_double_booking_overlap_rejected(anon):
    """BND-08: An overlapping date range on the same room is rejected."""
    first = anon.post(f"{BASE_URL}/api/bookings",
                      json=booking_payload(room_id=1, nights_from=1, nights_to=4))
    assert first.status_code == 201

    overlap = anon.post(f"{BASE_URL}/api/bookings",
                        json=booking_payload(room_id=1, nights_from=2, nights_to=3))
    assert overlap.status_code == 400
    assert "not available" in overlap.json()["error"].lower()


# ----------------------------------------------------------------- room bounds
def test_BND_09_room_price_zero_rejected(anon):
    """BND-09: A base price of 0 is rejected."""
    resp = anon.put(f"{BASE_URL}/api/rooms/1", json={"base_price": 0})
    assert resp.status_code == 400
    assert "greater than 0" in resp.json()["error"].lower()


# ------------------------------------------------------------ availability args
# --------------------------------------------------------------- not-found ids
# -------------------------------------------------------------- database bounds
def test_BND_10_room_number_uniqueness_enforced():
    """BND-10: The UNIQUE constraint on rooms.room_number is enforced by the DB."""
    conn = db_connect()
    cur = conn.cursor()
    with pytest.raises(mysql.connector.Error):
        cur.execute(
            "INSERT INTO rooms (room_number, room_type, base_price, status, floor) "
            "VALUES ('101', 'Duplicate', 1000.00, 'available', 1)"
        )
        conn.commit()
    conn.rollback()
    cur.close()
    conn.close()


def test_BND_11_oversized_input_handled_gracefully(anon):
    """
    BND-11: A guest name far longer than VARCHAR(100) must be handled gracefully
    (rejected with 4xx), not crash the server.

    KNOWN DEFECT — the insert is unguarded, so MySQL strict mode raises
    'Data too long' and the request returns HTTP 500.
    """
    resp = anon.post(f"{BASE_URL}/api/bookings",
                     json=booking_payload(room_id=1, guest_name="A" * 200))
    assert resp.status_code < 500, (
        f"Oversized input should be handled, but returned {resp.status_code} "
        "(unhandled DB error)."
    )


@pytest.mark.demo
def test_BND_12_empty_string_required_field_rejected(anon):
    """
    BND-12: A present-but-blank required field must be rejected.

    KNOWN DEFECT D6 — the API only checks that the key exists, not that it holds
    a value, so a blank guest name is accepted and a booking is created.
    """
    resp = anon.post(f"{BASE_URL}/api/bookings",
                     json=booking_payload(room_id=1, guest_name=""))
    assert resp.status_code == 400, (
        f"Expected 400 for a blank guest_name, got {resp.status_code} "
        "(API checks key presence only, not that the value is non-empty). Defect D6."
    )


# ----------------------------------------------------- UI form bounds (fixed)
def test_BND_13_booking_form_rejects_reversed_dates(manager):
    """BND-13: The /new-booking form rejects check-out before check-in. (FIXED: D2)"""
    resp = manager.post(f"{BASE_URL}/new-booking", data={
        "guest_name": "Reverse Date",
        "guest_email": "rev@example.com",
        "guest_phone": "9876543210",
        "room_id": "1",
        "check_in": day(5),
        "check_out": day(2),
    })
    assert resp.status_code == 400
    assert "check-out must be after check-in" in resp.text.lower()
    # and no booking leaked into the database
    assert query_one("SELECT COUNT(*) AS c FROM bookings")["c"] == 0


