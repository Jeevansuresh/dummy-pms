"""
CATEGORY 1 — Functional End-to-End (E2E) Paths  [UI layer, Playwright]

Browser-driven user journeys. Every test captures a screenshot into
test_evidence/screenshots/ for the Part B demo document.

Covers: E2E-01, E2E-03, E2E-04, E2E-05
Plus:   INT-05 (UI -> database -> API round trip)
"""
import pytest

from conftest import BASE_URL, day, query_one

pytestmark = pytest.mark.ui


def shot(page, shots, name):
    """Capture a full-page screenshot as test evidence."""
    page.screenshot(path=str(shots / f"{name}.png"), full_page=True)


def test_E2E_01_login_as_manager(page, shots):
    """E2E-01: A manager signs in and lands on the dashboard."""
    page.goto(f"{BASE_URL}/login")
    page.fill("input[name='username']", "manager")
    page.fill("input[name='password']", "manager123")
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")

    assert "/dashboard" in page.url
    assert "Hotel Manager" in page.content()
    shot(page, shots, "E2E-01_2_dashboard_after_login")


@pytest.mark.demo
def test_E2E_03_create_booking_through_the_form(page, shots, ui_login):
    """E2E-03: A receptionist creates a booking through the UI form."""
    ui_login("reception")
    page.goto(f"{BASE_URL}/new-booking")
    page.wait_for_load_state("networkidle")

    page.fill("input[name='guest_name']", "Anita Kumar")
    page.fill("input[name='guest_email']", "anita.kumar@example.com")
    page.fill("input[name='guest_phone']", "9845012345")
    page.fill("input[name='id_proof']", "AADHAAR-1234")
    page.select_option("select[name='room_id']", "1")
    page.fill("input[name='check_in']", day(1))
    page.fill("input[name='check_out']", day(3))
    shot(page, shots, "E2E-03_1_booking_form_filled")

    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")

    assert "/bookings" in page.url
    assert "Anita Kumar" in page.content()
    shot(page, shots, "E2E-03_2_booking_created")

    # verify it really reached the database and the room flipped to occupied
    assert query_one("SELECT COUNT(*) AS c FROM bookings")["c"] == 1
    assert query_one("SELECT status FROM rooms WHERE room_id=1")["status"] == "occupied"


@pytest.mark.demo
def test_E2E_04_full_stay_lifecycle(page, shots, ui_login):
    """E2E-04: confirmed -> checked_in -> checked_out, with the room freed at the end."""
    ui_login("reception")

    # create the booking
    page.goto(f"{BASE_URL}/new-booking")
    page.fill("input[name='guest_name']", "Ravi Shankar")
    page.fill("input[name='guest_email']", "ravi@example.com")
    page.fill("input[name='guest_phone']", "9845099999")
    page.select_option("select[name='room_id']", "2")
    page.fill("input[name='check_in']", day(1))
    page.fill("input[name='check_out']", day(2))
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")

    booking = query_one("SELECT booking_id, status FROM bookings LIMIT 1")
    assert booking["status"] == "confirmed"
    shot(page, shots, "E2E-04_1_status_confirmed")

    # check in
    page.goto(f"{BASE_URL}/bookings/update-status/{booking['booking_id']}/checked_in")
    page.wait_for_load_state("networkidle")
    assert query_one("SELECT status FROM bookings WHERE booking_id=%s",
                     (booking["booking_id"],))["status"] == "checked_in"
    shot(page, shots, "E2E-04_2_status_checked_in")

    # check out
    page.goto(f"{BASE_URL}/bookings/update-status/{booking['booking_id']}/checked_out")
    page.wait_for_load_state("networkidle")
    assert query_one("SELECT status FROM bookings WHERE booking_id=%s",
                     (booking["booking_id"],))["status"] == "checked_out"
    # room must be released
    assert query_one("SELECT status FROM rooms WHERE room_id=2")["status"] == "available"
    shot(page, shots, "E2E-04_3_status_checked_out_room_freed")


def test_E2E_05_edit_room_price_persists(page, shots, ui_login):
    """E2E-05: A price change made in the UI is saved to the database. (FIXED)"""
    ui_login("manager")
    page.goto(f"{BASE_URL}/rooms/edit/3")
    page.wait_for_load_state("networkidle")

    page.fill("input[name='base_price']", "5000")
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")

    assert "/rooms" in page.url
    stored = float(query_one("SELECT base_price FROM rooms WHERE room_id=3")["base_price"])
    assert stored == 5000.00, f"price change was not persisted (DB still holds {stored})"
    shot(page, shots, "E2E-05_2_price_updated")


def test_INT_05_ui_write_is_visible_through_the_api(page, shots, ui_login):
    """INT-05: A booking created in the UI is returned by the REST API (shared DB)."""
    ui_login("reception")
    page.goto(f"{BASE_URL}/new-booking")
    page.fill("input[name='guest_name']", "Integration Check")
    page.fill("input[name='guest_email']", "integration@example.com")
    page.fill("input[name='guest_phone']", "9845022222")
    page.select_option("select[name='room_id']", "6")
    page.fill("input[name='check_in']", day(2))
    page.fill("input[name='check_out']", day(5))
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    shot(page, shots, "INT-05_1_created_in_ui")

    # read the same record back through the API
    page.goto(f"{BASE_URL}/api/bookings")
    api_text = page.inner_text("body")
    assert "Integration Check" in api_text
    assert "integration@example.com" in api_text
    shot(page, shots, "INT-05_2_same_record_via_api")
