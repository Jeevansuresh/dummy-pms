"""
CATEGORY 3 — Integration Points

Data-flow validation between frontend, API and database, plus cross-entity
consistency and role-based access control.
Covers: INT-01 .. INT-04, INT-06 .. INT-09   (INT-05 is a UI test)
"""
import pytest
import requests

from conftest import (BASE_URL, booking_payload, db_connect, day, query_all,
                      query_one)


def test_INT_01_booking_persists_to_database(anon, manager):
    """INT-01: A booking created via the API is readable back from the database."""
    created = anon.post(f"{BASE_URL}/api/bookings", json=booking_payload(room_id=1)).json()["data"]
    bid = created["booking_id"]

    row = query_one("SELECT * FROM bookings WHERE booking_id=%s", (bid,))
    assert row is not None, "booking was not written to the database"
    assert row["room_id"] == 1
    assert str(row["check_in"]) == created["check_in"]
    assert str(row["check_out"]) == created["check_out"]

    fetched = manager.get(f"{BASE_URL}/api/bookings/{bid}").json()["data"]
    assert fetched["booking_id"] == bid
    assert fetched["room_id"] == row["room_id"]


@pytest.mark.demo
def test_INT_02_booking_sets_room_occupied(anon):
    """INT-02: Creating a booking cascades the room status to 'occupied'."""
    created = anon.post(f"{BASE_URL}/api/bookings", json=booking_payload(room_id=4)).json()["data"]

    room = query_one("SELECT * FROM rooms WHERE room_id=4")
    assert room["status"] == "occupied"
    assert room["current_booking_id"] == created["booking_id"]
    assert room["current_guest_id"] == created["guest_id"]

    api_room = anon.get(f"{BASE_URL}/api/rooms/4").json()["data"]
    assert api_room["status"] == "occupied"


def test_INT_03_checkout_frees_the_room(anon, manager):
    """INT-03: Checking out cascades the room back to 'available'."""
    created = anon.post(f"{BASE_URL}/api/bookings", json=booking_payload(room_id=4)).json()["data"]
    bid = created["booking_id"]
    assert query_one("SELECT status FROM rooms WHERE room_id=4")["status"] == "occupied"

    resp = manager.put(f"{BASE_URL}/api/bookings/{bid}", json={"status": "checked_out"})
    assert resp.status_code == 200

    room = query_one("SELECT * FROM rooms WHERE room_id=4")
    assert room["status"] == "available"
    assert room["current_guest_id"] is None


def test_INT_04_total_price_computed_from_room_and_nights(anon):
    """INT-04: total_price == room base price x number of nights."""
    # room 5 = Suite @ 6000, 3 nights
    created = anon.post(f"{BASE_URL}/api/bookings",
                        json=booking_payload(room_id=5, nights_from=1, nights_to=4)).json()["data"]

    assert float(created["total_price"]) == 18000.00

    row = query_one("SELECT total_price FROM bookings WHERE booking_id=%s",
                    (created["booking_id"],))
    assert float(row["total_price"]) == 18000.00


# ------------------------------------------------------------------ RBAC flows
@pytest.mark.demo
def test_INT_06_auditor_cannot_mutate_bookings(anon, auditor):
    """INT-06: The auditor role is forbidden from cancelling a booking."""
    created = anon.post(f"{BASE_URL}/api/bookings", json=booking_payload(room_id=1)).json()["data"]

    resp = auditor.delete(f"{BASE_URL}/api/bookings/{created['booking_id']}")
    assert resp.status_code == 403
    assert "forbidden" in resp.json()["error"].lower()


def test_INT_07_unauthenticated_api_access_blocked(anon):
    """INT-07: A guarded endpoint rejects unauthenticated access with 401."""
    resp = anon.get(f"{BASE_URL}/api/guests")
    assert resp.status_code == 401
    assert "authentication required" in resp.json()["error"].lower()


# ----------------------------------------------------- known integration defects
@pytest.mark.demo
def test_INT_08_room_update_persists_to_database(anon):
    """
    INT-08: PUT /api/rooms/<id> must persist the new price to the database.

    KNOWN DEFECT D3 — the handler mutates a throwaway dict and never writes to
    MySQL, yet still reports 'Room updated successfully'.
    """
    resp = anon.put(f"{BASE_URL}/api/rooms/1", json={"base_price": 9999})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    after = anon.get(f"{BASE_URL}/api/rooms/1").json()["data"]
    assert float(after["base_price"]) == 9999.00, (
        f"PUT reported success but GET still returns {after['base_price']}; "
        "the update was never persisted to MySQL. Defect D3."
    )


@pytest.mark.demo
def test_INT_09_api_booking_creation_requires_auth(anon):
    """
    INT-09: Creating a booking is a mutation and must require authentication.

    KNOWN DEFECT D4 — /api/bookings carries no auth decorator, so an anonymous
    caller can create bookings freely.
    """
    resp = anon.post(f"{BASE_URL}/api/bookings", json=booking_payload(room_id=1))
    assert resp.status_code == 401, (
        f"Anonymous booking creation returned {resp.status_code}; "
        "the endpoint has no authentication guard (defect D4)."
    )
