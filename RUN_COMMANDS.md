# Demo Commands — copy & paste

**Jeevan S · 24BCE1862 · BCSE301L SWE DA3**

Run everything from the project folder:

```
cd D:\everything\cyberattacks\dummy-pms
```

Every command below starts the app automatically and resets the database first,
so they can be run in any order, as many times as you like.

---

## 0. Before you start — is MySQL running?

```
powershell "Get-Service MySQL80"
```

Expected: `Running`. If it says Stopped:

```
powershell "Start-Service MySQL80"
```

---

## 1. Run the FULL suite — all 30 tests

```
python -m pytest -v
```

Expected: **24 passed, 6 failed** in about 20 seconds.

---

## 2. Run each category on its own

### Category 1 — Functional End-to-End (E2E) Paths

```
python -m pytest -k "test_E2E" -v
```

Expected: **8 tests — 7 passed, 1 failed** (E2E-08 lockout defect).

### Category 2 — Boundary & Edge Cases

```
python -m pytest -k "test_BND" -v
```

Expected: **13 tests — 10 passed, 3 failed** (BND-05, BND-11, BND-12).

### Category 3 — Integration Points

```
python -m pytest -k "test_INT" -v
```

Expected: **9 tests — 7 passed, 2 failed** (INT-08, INT-09).

---

## 3. Watch the browser drive the application

This opens a real Chrome window and fills in the booking form by itself,
checks a guest in, then checks them out. **This is the one to show her.**

```
python -m pytest tests/test_category1_e2e_ui.py -k "E2E_03 or E2E_04" --headed --slowmo 700
```

Expected: **2 passed** in about 20 seconds.

To watch *all five* browser tests instead (takes about a minute):

```
python -m pytest tests/test_category1_e2e_ui.py --headed --slowmo 700
```

---

## 4. The short demo set — 11 tests, failures easy to read

Use this when talking through the defects: fewer lines on screen, so the red
failures stay visible without scrolling.

```
python -m pytest -m demo -v
```

Expected: **6 passed, 5 failed** in about 7 seconds.

---

## 5. Show only the failures (the defects found)

```
python -m pytest -v --tb=line -rf
```

The summary at the bottom lists each failure with the defect it proves.

---

## 6. Run one single test

```
python -m pytest -k "test_BND_08" -v
```

That one is the double-booking check. Any test ID works — swap in
`test_E2E_04`, `test_INT_08`, and so on.

---

## 7. Generate the HTML report

```
python -m pytest --html=test_evidence/report.html --self-contained-html
```

Then open `test_evidence\report.html` in a browser.

---

## 8. Open the final report document

```
start test_evidence\DEMO_DOCUMENT.pdf
```

or the scrollable version:

```
start test_evidence\DEMO_DOCUMENT.html
```

---

## 9. Rebuild the whole report from scratch (only if asked)

```
python -m pytest -v --tb=line --html=test_evidence/report.html --self-contained-html > test_evidence/console_output.txt 2>&1
python tools/capture_evidence.py
python tools/render_api_cards.py
python tools/build_demo_document.py
python tools/export_pdf.py
```

---

## The 6 failures and what each one caught

| Test | Defect |
|------|--------|
| `E2E-08` | **D1** — account lockout never triggers; the helper functions are never called |
| `BND-05` | **D7** — a malformed date returns HTTP 500 instead of a clean 400 |
| `BND-11` | **D8** — oversized input hits the database unguarded and returns 500 |
| `BND-12` | **D6** — a blank required field is accepted; only key presence is checked |
| `INT-08` | **D3** — `PUT /api/rooms` reports success but never writes to MySQL |
| `INT-09` | **D4** — a booking can be created with no authentication at all |

They are **intentional**. They are real defects left in the build so the
automation can be seen catching them — at least one in every category.
Three others (D2, D5, D9) were found and fixed; their tests now pass.

---

## If something goes wrong

| Problem | Fix |
|---------|-----|
| MySQL not running | `powershell "Start-Service MySQL80"` |
| Address already in use | `set PMS_TEST_PORT=5056` then run again |
| Everything fails | `mysql -u root -p < schema.sql` to reload the seed data |
| Browser won't open | Drop `--headed`; the screenshots in the PDF cover it |
| Total failure | Open `test_evidence\DEMO_DOCUMENT.pdf` — it has every screenshot from a real run |
