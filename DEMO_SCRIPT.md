# Part B — Live Demo Run Sheet

**Total time: ~8 minutes.** You never walk through all 30 tests one by one — you run them.
The suite finishing in under 15 seconds *is* the demonstration.

---

## Before class (5 minutes, do this once)

```bash
# 1. MySQL running?
powershell "Get-Service MySQL80"

# 2. Schema loaded + app starts?
python app.py          # visit http://localhost:5000, then Ctrl+C

# 3. Dry-run the whole thing so nothing surprises you
python -m pytest -v
```

Have these open in tabs before you start:
1. A terminal in `D:\everything\cyberattacks\dummy-pms`
2. `test_evidence/DEMO_DOCUMENT.html` in a browser (better for scrolling live)
3. `PART_A_TEST_CASES.md` (for Part A questions)

**To submit:** `test_evidence/DEMO_DOCUMENT.pdf` — 34 pages, A4, page-numbered.
Regenerate it any time with `python tools/export_pdf.py`.

> **Safety net:** every test resets the DB to the same 8-room seed state, so you can re-run
> any command as many times as you like. Nothing drifts.

---

## ACT 1 — The application (1.5 min)

```bash
python app.py
```

Open `http://localhost:5000`, log in as `manager / manager123`.

**Say:** *"This is a Property Management System for an 8-room serviced apartment —
rooms, guests, and the full booking lifecycle, with a REST API behind the same database.
Three roles: manager, reception, auditor."*

Click: Dashboard → Rooms → New Booking. Then **Ctrl+C** to stop the server.

> The test suite starts its own server on port 5055, so leaving this one running is fine
> either way — but stopping it avoids confusion.

---

## ACT 2 — Watch the automation drive the app (30 sec runtime, ~2 min with talking)

```bash
python -m pytest tests/test_category1_e2e_ui.py -k "E2E_03 or E2E_04" --headed --slowmo 700
```

A real Chrome window opens and drives the app by itself: fills the booking form, submits,
checks the guest in, checks them out.

**Say:** *"This is Playwright driving a real browser — the same journey a receptionist does.
E2E-03 creates the booking, E2E-04 runs the full lifecycle: confirmed → checked in →
checked out, and asserts in SQL that the room was released at the end."*

⏱ Takes about 20 seconds. **This is your money shot — don't rush it.**

---

## ACT 3 — The full suite (30 sec)

```bash
python -m pytest -v
```

**Say:** *"30 automated test cases across the three required categories — end-to-end
journeys, boundary and edge cases, and integration points. Under fifteen seconds, fully
automated, against a database reset before every single test."*

Let it finish. Point at the last line: **`6 failed, 24 passed`**.

---

## ACT 4 — The failures are the point (3 min)

```bash
python -m pytest -m demo -v
```

11 curated tests of the 30, ~7 seconds — all three categories, 6 pass and 5 fail, so the red lines
are easy to read on screen without scrolling.

**Say:** *"24 of 30 pass. The 6 failures aren't broken tests — they're real defects the
suite caught, and there's at least one in every category."*

Then walk the failures (they're on screen, with the defect ref in each message):

| Test | Category | What it caught |
|------|----------|----------------|
| `E2E-08` | E2E | **D1** — the lockout code exists but `/login` never calls it, so an account never locks after 5 bad passwords |
| `BND-05` | Boundary | **D7** — a malformed date crashes with HTTP 500 instead of a clean 400 |
| `BND-11` | Boundary | **D8** — an oversized name hits the DB unguarded and returns a 500 |
| `BND-12` | Boundary | **D6** — a blank required field is accepted, because the API only checks the key exists |
| `INT-08` | Integration | **D3** — `PUT /api/rooms` reports "updated successfully" but writes nothing to MySQL |
| `INT-09` | Integration | **D4** — anyone can create a booking with no authentication at all |

**Then the strong close:** *"I also found and fixed three more during this exercise —
missing validation on the booking form, a room-edit form that silently saved nothing, and
a database connection leak that left transactions holding table locks. Those tests now
pass, and that's the evidence the fixes work."*

---

## ACT 5 — Hand over the document (1 min)

Open `test_evidence/DEMO_DOCUMENT.html`.

**Say:** *"Everything is documented here — the software and its architecture, all 30 test
cases with their results, and screenshots captured automatically during the run."*

Scroll: results table → a UI test card with its screenshot → defects section.

---

## If something goes wrong

| Problem | Fix |
|---------|-----|
| MySQL not running | `powershell "Start-Service MySQL80"` |
| "Address already in use" | Another app on 5055: `set PMS_TEST_PORT=5056` then re-run |
| Browser doesn't appear | Drop `--headed`; the screenshots in the document cover it |
| Everything fails | Reload the seed data: `mysql -u root -p < schema.sql` |
| **Total failure** | Open `DEMO_DOCUMENT.html` — it has every screenshot from a real run |

---

## Likely questions

**"Why do some tests fail?"**
They're genuine defects in the build. A test suite that only ever goes green isn't proving
anything — these demonstrate the automation actually detects broken behaviour. All six are
documented with root causes in `PART_A_TEST_CASES.md` §6.

**"How did you choose the test cases?"**
Three categories from the brief: critical user journeys end-to-end, boundary and edge cases
on every input, and integration points where data crosses the UI → API → database boundary.
Full matrix in `PART_A_TEST_CASES.md`.

**"How do you know the tests are reliable?"**
Every test resets the database to the same seed state first, and uses dynamic future dates,
so there's no shared state or ordering dependency. Re-run it right now and you get an
identical result.

**"Why two different tools?"**
Playwright drives the real browser to prove the user journeys work; pytest + requests test
the API contract and assert directly in SQL that data actually persisted. UI tests alone
can't prove the database was written to — that's what the integration layer checks.

**"What would you fix first?"**
D4 — unauthenticated booking creation. It's the only one with a security impact.
Then D3, because an API reporting success while silently discarding writes is the kind of
bug that corrupts data without anyone noticing.
