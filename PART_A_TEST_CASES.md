# Part A — Automated Test Case Specification

**Application Under Test (AUT):** Chennai BnB — Property Management System (PMS)
**Stack:** Python / Flask (server-rendered UI + REST API) + MySQL
**Prepared for:** Software Engineering Assignment — Test Case Generation & Automation
**Date:** 2026-10-21

---

## 1. Purpose & Scope

This document is **Part A** of the assignment: a detailed, automation-ready test-case
catalogue for the Chennai BnB PMS. Test cases are written so each one can be executed by an
automation script and produce a clear pass/fail result (suitable for screenshotting).

Cases are grouped into the three required categories:

1. **Functional End-to-End (E2E) Paths** — critical user journeys via the UI/API.
2. **Boundary & Edge Cases** — field validation, min/max inputs, error handling.
3. **Integration Points** — data flow between frontend → API → database.

Each case specifies the recommended **automation layer**:
- **UI** — browser automation (Playwright or Selenium) against the rendered pages.
- **API** — HTTP automation (`pytest` + `requests`, or Postman/Newman) against `/api/*`.

---

## 2. Application Under Test — Reference

### 2.1 How to run (test environment setup)

```bash
# 1. Start MySQL and load schema + seed data (8 rooms)
mysql -u root -p < schema.sql

# 2. Set env (dev mode disables the secure-cookie requirement)
set FLASK_ENV=development            # Windows
export FLASK_ENV=development         # Linux/macOS

# 3. Run the app
python app.py                        # serves http://localhost:5000
```

**Base URL:** `http://localhost:5000`

### 2.2 Demo accounts (login credentials)

| Username   | Password       | Role       |
|------------|----------------|------------|
| `manager`   | `manager123`   | manager    |
| `reception` | `reception123` | reception  |
| `auditor`   | `auditor123`   | auditor    |

### 2.3 Seed data

8 rooms (`101`–`108`), floors 1–2, types Deluxe (₹3500) / Premium (₹4500) / Suite (₹6000) /
Executive Suite (₹7500), all initially `available`. `guests` and `bookings` start empty.

### 2.4 Route map

**UI routes:** `/login`, `/logout`, `/`, `/dashboard`, `/rooms`, `/rooms/edit/<id>`,
`/bookings`, `/bookings/update-status/<id>/<status>`, `/new-booking`, `/guests`

**API routes:**

| Method(s)          | Endpoint                          | Auth required            |
|--------------------|-----------------------------------|--------------------------|
| GET                | `/api/hotel-info`                 | none                     |
| GET                | `/api/rooms`                      | none                     |
| GET, PUT           | `/api/rooms/<id>`                 | none                     |
| GET                | `/api/rooms/<id>/guest`           | manager/reception/auditor|
| GET                | `/api/rooms/available`            | manager/reception/auditor|
| GET, POST          | `/api/bookings`                   | none                     |
| GET, PUT, DELETE   | `/api/bookings/<id>`              | manager/reception        |
| GET                | `/api/guests`                     | manager/reception/auditor|
| GET                | `/api/guests/<id>`                | manager/reception/auditor|
| GET                | `/api/guests/checked-in`          | manager/reception/auditor|
| GET                | `/api/occupancy`                  | manager/reception/auditor|

**Auth-failure behaviour (needed for expected results):**
- UI page, not logged in → **302 redirect** to `/login?next=<path>`
- UI page, wrong role → **302 redirect** to `/dashboard` + flash message
- API, not logged in → **401** `{"error": "Authentication required"}`
- API, wrong role → **403** `{"error": "Forbidden: insufficient role"}`

**Booking status lifecycle:** `confirmed` → `checked_in` → `checked_out`; `cancelled` from any
active state. Creating a booking sets the room to `occupied`; `checked_out`/`cancelled` frees the
room back to `available` **only if no other active booking holds it**.

---

## 3. Category 1 — Functional End-to-End (E2E) Paths

Critical user journeys. Priority: **P1** = must pass for a working demo.

| ID | Test Case | Preconditions | Steps / Input | Expected Result | Layer | Priority |
|----|-----------|---------------|---------------|-----------------|-------|----------|
| E2E-01 | Successful login as manager | App running, no active session | Open `/login`; enter `manager` / `manager123`; submit | Redirect to `/dashboard`; welcome/display name "Hotel Manager" visible | UI | P1 |
| E2E-02 | Protected page requires login | No active session | Request `/dashboard` directly | 302 redirect to `/login?next=/dashboard` | UI | P1 |
| E2E-03 | Create a new booking (happy path) | Logged in; room 101 available | Open `/new-booking`; fill guest name/email/phone, pick room 101, check-in = today, check-out = today+2; submit | Redirect to `/bookings`; new booking listed; room 101 now `occupied` | UI | P1 |
| E2E-04 | Full stay lifecycle: book → check-in → check-out | Booking from E2E-03 exists, status `confirmed` | On `/bookings` trigger status → `checked_in`, then → `checked_out` | Status transitions confirmed → checked_in → checked_out; room 101 returns to `available` | UI | P1 |
| E2E-05 | Edit room price | Logged in; room 103 exists | Open `/rooms/edit/3`; change base price to 5000; submit | Room 103 price updated to ₹5000, **persisted to DB** and reflected on `/rooms` — **✅ PASS** (fixed: edit form previously did not persist) | UI | P2 |
| E2E-06 | API — create booking end to end | App running | `POST /api/bookings` with valid room_id + guest fields + valid dates | `201 Created`; `success:true`; booking has id, status `confirmed`, computed total_price | API | P1 |
| E2E-07 | Checked-in guests report | ≥1 booking in `checked_in` state | `GET /api/guests/checked-in` as reception | `200`; `data[]` lists the currently checked-in guest with room info | API | P2 |
| E2E-08 | Brute-force lockout journey | No active session | `POST /login` with `manager` + wrong password **6 times** in a row | 6th attempt should return a **locked-out** response (423/"account locked") — **⛔ EXPECTED FAIL** (defect D1: lockout never triggers) | UI/API | P1 |

---

## 4. Category 2 — Boundary & Edge Cases

Field validation, min/max inputs, malformed data, and error handling the automation must assert.

| ID | Test Case | Preconditions | Steps / Input | Expected Result | Layer | Priority |
|----|-----------|---------------|---------------|-----------------|-------|----------|
| BND-01 | Login with wrong password | — | `POST /login` `manager` / `wrongpass` | HTTP **401**; "Invalid credentials" flash; stays on login | UI/API | P1 |
| BND-02 | `open redirect` guard on `next` | — | Login with `?next=https://evil.com` | After login redirects to `/dashboard`, **not** the external URL (only `/`-prefixed paths honoured) | API | P2 |
| BND-03 | Booking — check-out equals check-in (0 nights) | — | `POST /api/bookings` check_in == check_out | **400** `"Check-out must be after check-in"` | API | P1 |
| BND-04 | Booking — check-out before check-in | — | `POST /api/bookings` check_out < check_in | **400** `"Check-out must be after check-in"` | API | P1 |
| BND-05 | Booking — invalid date format | — | `POST /api/bookings` check_in = `"2026/13/40"` | Should be **400** `"Invalid date format"` — **⛔ EXPECTED FAIL** (defect D7: uncaught `ValueError` leaks a 500) | API | P1 |
| BND-06 | Booking — missing required field | — | `POST /api/bookings` omit `guest_email` | **400** `"Missing required fields"` | API | P1 |
| BND-07 | Booking — non-existent room | — | `POST /api/bookings` room_id = 9999 | **404** `"Room not found"` | API | P1 |
| BND-08 | Booking — double-booking overlap rejected | Room 101 booked for D..D+3 | `POST /api/bookings` room 101 for D+1..D+2 (inside existing) | **400** `"Room not available"` | API | P1 |
| BND-09 | Room PUT — price = 0 rejected | — | `PUT /api/rooms/1` `{"base_price": 0}` | **400** `"Price must be greater than 0"` | API | P1 |
| BND-10 | Room number uniqueness (DB constraint) | Room `101` exists | Attempt to insert a second room with number `101` | DB rejects (UNIQUE constraint on `room_number`) | API/DB | P2 |
| BND-11 | Long input handling (field length) | — | Create guest with a 200-char name (field is `VARCHAR(100)`) | Should be handled gracefully (4xx), no crash — **⛔ EXPECTED FAIL** (defect D8: unguarded INSERT returns a 500) | API | P3 |
| BND-12 | Booking — empty-string required field rejected | — | `POST /api/bookings` with `guest_name = ""` (key present, value blank) + otherwise valid | Should return **400** (blank name rejected) — **⛔ EXPECTED FAIL** (defect D6: API checks key presence, not non-empty, so it returns 201) | API | P2 |
| BND-13 | Booking UI — reversed dates rejected | Logged in | On `/new-booking` submit check-out **before** check-in | **400** + "Check-out must be after check-in"; no booking created — **✅ PASS** (fixed: D2) | UI | P1 |

---

## 5. Category 3 — Integration Points

Data-flow validations between frontend → API → database and cross-entity consistency.

| ID | Test Case | Preconditions | Steps / Input | Expected Result | Layer | Priority |
|----|-----------|---------------|---------------|-----------------|-------|----------|
| INT-01 | Booking creation persists to DB | — | `POST /api/bookings` (valid), then `GET /api/bookings/<newId>` | GET returns same booking from DB with matching dates, room_id, guest_id | API→DB | P1 |
| INT-02 | Booking → room status cascade | Room 104 available | Create booking for room 104 via API, then `GET /api/rooms/4` | Room 104 status = `occupied`, `current_booking_id`/`current_guest` populated | API→DB | P1 |
| INT-03 | Check-out → room freed cascade | Room 104 occupied (INT-02) | `PUT /api/bookings/<id>` status `checked_out` as manager; then `GET /api/rooms/4` | Room 104 status = `available`; current guest cleared | API→DB | P1 |
| INT-04 | Total price computed from room price × nights | Room 105 price ₹6000 | `POST /api/bookings` room 105 for 3 nights | `total_price` = 18000 (3 × 6000) in response and DB | API→DB | P1 |
| INT-05 | UI form write is readable via API | — | Create booking through `/new-booking` UI; then `GET /api/bookings` | Booking created in the UI is returned by the API (shared DB) | UI→DB→API | P1 |
| INT-06 | RBAC — auditor blocked from booking mutation | Logged in as `auditor` | `DELETE /api/bookings/<id>` | **403** `"Forbidden: insufficient role"` (endpoint allows manager/reception only) | API | P1 |
| INT-07 | RBAC — unauthenticated API access blocked | No session | `GET /api/guests` | **401** `"Authentication required"` | API | P1 |
| INT-08 | Room PUT persistence (API) | Room 1 price = ₹3500 | `PUT /api/rooms/1` `{"base_price": 9999}`, then `GET /api/rooms/1` | GET should return 9999 — **⛔ EXPECTED FAIL** (defect D3: PUT returns "updated successfully" but writes nothing to DB; GET still shows 3500) | API→DB | P1 |
| INT-09 | API booking creation requires auth | No session | `POST /api/bookings` (valid body) **without logging in** | Should return **401** (mutation requires auth) — **⛔ EXPECTED FAIL** (defect D4: endpoint has no auth guard, returns 201) | API | P1 |

---

## 6. Defect Register (curated for the demo)

This build is intentionally a **mix of fixed and open defects**, so the automated run shows a
realistic pass/fail picture — most tests green (proving the suite and the app work) plus a few red
in **every category** (proving the suite actually catches bugs).

### 6.1 Fixed defects  *(→ their tests now PASS, which is what proves the fix)*

| Ref | Fix | Tests now green |
|-----|-----|-----------------|
| **D2** | `/new-booking` UI form now validates required fields, date format, check-out > check-in, and room availability (previously unguarded → 500 / negative-price bookings). | BND-13, E2E-03, E2E-04, INT-05 |
| **D5** | `/rooms/edit` UI form now **persists** price/status to MySQL and **validates** price > 0 (previously mutated a throwaway dict and saved nothing). | E2E-05 |
| **D9** | `create_guest()` / `create_booking()` leaked their DB connection when an INSERT failed, leaving an open transaction holding table locks. Both now release the connection in a `finally` block. | Unblocked the suite (BND-11 previously hung the run) |

### 6.2 Open defects  *(→ their tests FAIL — present these as findings)*

| Ref | Category | Defect | Failing test |
|-----|----------|--------|--------------|
| **D1** | E2E | Lockout helpers (`_is_login_locked`, `_record_failed_login`) exist but are **never called** by `/login` — brute-force lockout never triggers. | **E2E-08** |
| **D7** | Boundary | `POST /api/bookings` runs the availability check (which parses dates) *before* the guarded try/except, so a malformed date raises an uncaught `ValueError` → **HTTP 500** instead of 400. | **BND-05** |
| **D8** | Boundary | The guest INSERT is unguarded, so an oversized name hits MySQL strict mode (`Data too long`) and returns **HTTP 500** instead of a validation error. | **BND-11** |
| **D6** | Boundary | `POST /api/bookings` checks only that required keys are *present*, not *non-empty* — a blank `guest_name` is accepted (201). | **BND-12** |
| **D3** | Integration | `PUT /api/rooms/<id>` reports `"updated successfully"` but **does not persist** to the DB (mutates a throwaway dict). | **INT-08** |
| **D4** | Integration | `/api/bookings` (GET/POST) and `/api/rooms` (GET/PUT) have **no auth guard** — mutations work unauthenticated, inconsistent with the role-guarded endpoints. | **INT-09** |

---

## 7. Actual Results Matrix  *(measured — full suite run, ~14s)*

| Category | Total | PASSED | FAILED (ID → defect) |
|----------|-------|--------|----------------------|
| 1. Functional E2E Paths | 8 | 7 | **E2E-08** → D1 |
| 2. Boundary & Edge Cases | 13 | 10 | **BND-05** → D7, **BND-11** → D8, **BND-12** → D6 |
| 3. Integration Points | 9 | 7 | **INT-08** → D3, **INT-09** → D4 |
| **Total** | **30** | **24** | **6** |

> **Demo talking point:** "24 of 30 automated checks pass in about 14 seconds. The 6 failures are
> genuine defects the suite caught, with at least one in every category: a broken business rule
> (D1 — lockout never fires), three input-validation gaps (D7/D8 leak HTTP 500s on malformed and
> oversized input, D6 accepts blank required fields), a silent persistence bug (D3 — the API
> reports success but writes nothing), and a missing authorization guard (D4 — anyone can create
> a booking). Three further defects (D2, D5, D9) were found during this exercise and fixed, and
> their now-passing tests are the evidence the fixes work."

**Recommended Part B automation stack:**
- **API layer:** `pytest` + `requests` — fast, deterministic; screenshot the terminal run or an
  HTML report (`pytest --html=report.html`). Mark the 6 known-failing cases with `xfail` if you
  want a clean exit code while still showing them as caught defects.
- **UI layer:** **Playwright** (recommended) or Selenium — for the E2E journeys and UI boundary
  cases; screenshot-on-failure is ideal Part B evidence.
- **Run order:** reset DB (reload `schema.sql`) → API suite → UI suite, so every run starts from
  the known 8-room seed state.
