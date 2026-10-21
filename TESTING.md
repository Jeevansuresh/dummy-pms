# Automated Test Suite — Quick Start

30 automated test cases covering the Chennai BnB PMS, organised into the three
assignment categories. Current result: **24 passed, 6 failed** (~14s).

## One-time setup

```bash
# 1. Load the database schema and seed data
mysql -u root -p < schema.sql

# 2. Install test dependencies
pip install -r requirements-test.txt
python -m playwright install chromium
```

## Running the tests

| What | Command |
|------|---------|
| **Everything** (starts the app automatically) | `python -m pytest -v` |
| **Curated demo subset** (11 of 30, ~7s, all 3 categories) | `python -m pytest -m demo -v` |
| Category 1 — E2E (API) | `python -m pytest tests/test_category1_e2e_api.py -v` |
| Category 1 — E2E (browser) | `python -m pytest tests/test_category1_e2e_ui.py -v` |
| Category 2 — Boundary & edge | `python -m pytest tests/test_category2_boundary.py -v` |
| Category 3 — Integration | `python -m pytest tests/test_category3_integration.py -v` |
| One single test | `python -m pytest tests/test_category2_boundary.py::test_BND_08_double_booking_overlap_rejected -v` |
| **Watch the browser drive the app** | `python -m pytest tests/test_category1_e2e_ui.py --headed --slowmo 600` |
| With HTML report | `python -m pytest --html=test_evidence/report.html --self-contained-html` |

## Regenerating the demo document

```bash
python -m pytest -v --tb=line --html=test_evidence/report.html --self-contained-html > test_evidence/console_output.txt 2>&1
python tools/capture_evidence.py      # console + report screenshots
python tools/render_api_cards.py      # one evidence card per API/DB test
python tools/build_demo_document.py   # assembles the final document
python tools/export_pdf.py            # A4 PDF with page numbers (for submission)
```

Produces `test_evidence/DEMO_DOCUMENT.html` — open it in any browser
(Ctrl+P → Save as PDF to submit).

## Layout

```
tests/
  conftest.py                   fixtures: live server, DB reset, auth sessions
  test_category1_e2e_api.py     E2E journeys via the REST API
  test_category1_e2e_ui.py      E2E journeys via Playwright (captures screenshots)
  test_category2_boundary.py    validation, min/max, malformed input
  test_category3_integration.py API↔DB data flow and RBAC
tools/
  capture_evidence.py           renders the run output to PNG evidence
  render_api_cards.py           one evidence card per API/DB test
  build_demo_document.py        builds the final HTML report document
  export_pdf.py                 exports that document to A4 PDF
test_evidence/
  DEMO_DOCUMENT.pdf             ← submit this (1.5 MB, 34 pages, A4)
  DEMO_DOCUMENT.html            ← present this (2.6 MB, opens offline)
  screenshots/                  38 PNGs (9 browser + 25 API cards + 4 run evidence)
  api_exchanges.json            real HTTP exchanges recorded during the run
  report.html                   pytest HTML report
  console_output.txt            raw pytest output
```

**Evidence coverage:** all 30 test cases have their own image. UI tests get real browser
screenshots; API and database tests get a card showing the actual HTTP request/response
captured live during the run, plus the real assertion lines from the test source.

## Note on the 6 failures

They are **intentional and genuine** — real defects left in the build so the suite can be
seen catching them, with at least one in every category. Full explanation in
`PART_A_TEST_CASES.md` §6, and in the demo document.

| Test | Defect |
|------|--------|
| `E2E-08` | D1 — account lockout never triggers (helpers never called) |
| `BND-05` | D7 — malformed date leaks an HTTP 500 instead of 400 |
| `BND-11` | D8 — oversized input leaks an HTTP 500 |
| `BND-12` | D6 — blank required field accepted |
| `INT-08` | D3 — `PUT /api/rooms` reports success but persists nothing |
| `INT-09` | D4 — booking creation needs no authentication |

**Test isolation:** every test resets the database to the same 8-room seed state, so the
suite is deterministic and safe to re-run live, repeatedly.
