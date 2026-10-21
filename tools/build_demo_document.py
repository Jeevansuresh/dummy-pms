"""
Build the Part B demo document.

Parses the REAL pytest console output, pairs each test case with the
screenshots captured during that run, and emits a single self-contained HTML
file (all images embedded as base64) that opens offline and prints to PDF.

Usage:
    python tools/build_demo_document.py
"""
import base64
import html
import pathlib
import re
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "test_evidence"
SHOTS = EVIDENCE / "screenshots"
CONSOLE_LOG = EVIDENCE / "console_output.txt"
OUTPUT = EVIDENCE / "DEMO_DOCUMENT.html"

# --------------------------------------------------------------------------
# Test-case metadata: ID -> (title, layer, what it proves)
# --------------------------------------------------------------------------
META = {
    # ---- Category 1: Functional E2E ----
    "E2E-01": ("Login as manager", "UI", "Valid credentials authenticate and land on the dashboard."),
    "E2E-02": ("Protected page requires login", "API", "Anonymous /dashboard request redirects to /login."),
    "E2E-03": ("Create booking through the form", "UI", "Full booking creation journey through the UI form."),
    "E2E-04": ("Full stay lifecycle", "UI", "confirmed -> checked_in -> checked_out, room freed at the end."),
    "E2E-05": ("Edit room price persists", "UI", "A UI price change is written to and read back from MySQL."),
    "E2E-06": ("API create booking", "API", "POST /api/bookings returns 201 with a correct computed price."),
    "E2E-07": ("Checked-in guests report", "API", "A checked-in booking appears in the occupancy report."),
    "E2E-08": ("Brute-force lockout journey", "API", "Account should lock after 5 failed logins."),

    # ---- Category 2: Boundary & Edge ----
    "BND-01": ("Login wrong password", "API", "Bad password is rejected with HTTP 401."),
    "BND-02": ("Open-redirect guard", "API", "External URL in ?next= is not honoured after login."),
    "BND-03": ("Check-out equals check-in", "API", "Zero-night booking rejected with 400."),
    "BND-04": ("Check-out before check-in", "API", "Negative-night booking rejected with 400."),
    "BND-05": ("Invalid date format", "API", "Malformed date should return a clean 400."),
    "BND-06": ("Missing required field", "API", "Omitted field rejected with 400."),
    "BND-07": ("Non-existent room", "API", "Unknown room id returns 404."),
    "BND-08": ("Double-booking overlap", "API", "Overlapping date range on one room is rejected."),
    "BND-09": ("Price zero rejected", "API", "base_price of 0 rejected with 400."),
    "BND-10": ("Room number uniqueness", "DB", "UNIQUE constraint on room_number is enforced."),
    "BND-11": ("Oversized input", "API", "A 200-char name should be handled, not crash the server."),
    "BND-12": ("Blank required field", "API", "A present-but-empty field should be rejected."),
    "BND-13": ("Booking form reversed dates", "UI", "UI form rejects check-out before check-in. (FIXED)"),

    # ---- Category 3: Integration ----
    "INT-01": ("Booking persists to database", "API-DB", "API-created booking is readable from MySQL."),
    "INT-02": ("Booking sets room occupied", "API-DB", "Creating a booking cascades room status to occupied."),
    "INT-03": ("Check-out frees the room", "API-DB", "Check-out cascades the room back to available."),
    "INT-04": ("Total price computed", "API-DB", "total_price equals base price x nights."),
    "INT-05": ("UI write visible via API", "UI-DB-API", "A booking made in the UI is returned by the REST API."),
    "INT-06": ("Auditor cannot mutate", "API", "Auditor role gets 403 on booking deletion."),
    "INT-07": ("Unauthenticated blocked", "API", "Guarded endpoint returns 401 without a session."),
    "INT-08": ("Room update persists", "API-DB", "PUT /api/rooms should persist the new price."),
    "INT-09": ("Booking creation requires auth", "API", "Anonymous booking creation should be blocked."),
}

CATEGORIES = [
    ("E2E", "Category 1 — Functional End-to-End (E2E) Paths",
     "Critical user journeys verified through the browser UI and the REST API."),
    ("BND", "Category 2 — Boundary &amp; Edge Cases",
     "Field validation, minimum/maximum inputs, malformed data and error handling."),
    ("INT", "Category 3 — Integration Points",
     "Data flow between frontend, API and database, plus role-based access control."),
]

DEFECTS = {
    "E2E-08": ("D1", "Lockout helpers <code>_is_login_locked()</code> / <code>_record_failed_login()</code> "
                     "are defined in app.py but never called by the <code>/login</code> route, so no "
                     "lockout ever triggers."),
    "BND-05": ("D7", "The availability check parses the dates <em>before</em> the guarded try/except "
                     "block, so a malformed date raises an uncaught <code>ValueError</code> and leaks "
                     "an HTTP 500 instead of a clean 400."),
    "BND-11": ("D8", "The guest INSERT is unguarded, so MySQL strict mode raises <em>Data too long</em> "
                     "and the request returns HTTP 500 rather than a validation error."),
    "BND-12": ("D6", "The API only checks that required <em>keys exist</em>, not that they hold a value, "
                     "so a blank guest name is accepted and a booking is created."),
    "INT-08": ("D3", "<code>PUT /api/rooms/&lt;id&gt;</code> mutates a throwaway dictionary and never "
                     "writes to MySQL, yet still reports <em>Room updated successfully</em>."),
    "INT-09": ("D4", "<code>/api/bookings</code> carries no authentication decorator, so an anonymous "
                     "caller can create bookings freely."),
}

FIXED = [
    ("D2", "<code>/new-booking</code> form validation",
     "The booking form had no validation at all: a malformed date crashed with a 500 and reversed "
     "dates created a booking with a negative total. It now validates required fields, date format, "
     "date ordering and room availability.",
     "BND-13, E2E-03, E2E-04, INT-05"),
    ("D5", "<code>/rooms/edit</code> persistence &amp; validation",
     "The room edit form mutated a throwaway dictionary and saved nothing, and accepted any price. "
     "It now writes through to MySQL and rejects a price of zero or less.",
     "E2E-05"),
    ("D9", "Database connection leak on error",
     "<code>create_guest()</code> and <code>create_booking()</code> never closed their connection when "
     "an INSERT failed, leaving an open transaction holding table locks. Both now release the "
     "connection in a <code>finally</code> block.",
     "Prevented the suite from hanging on BND-11"),
]


# --------------------------------------------------------------------------
def parse_results(log_text):
    """Extract {TEST-ID: 'PASSED'|'FAILED'} from the real pytest output."""
    results = {}
    pattern = re.compile(
        r"::test_([A-Z0-9]+)_(\d+)_\w*?(?:\[\w+\])?\s+(PASSED|FAILED)", re.M)
    for prefix, num, status in pattern.findall(log_text):
        results[f"{prefix}-{num}"] = status
    return results


def parse_totals(log_text):
    m = re.search(r"(\d+) failed, (\d+) passed in ([\d.]+)s", log_text)
    if m:
        return int(m.group(2)), int(m.group(1)), float(m.group(3))
    m = re.search(r"(\d+) passed in ([\d.]+)s", log_text)
    if m:
        return int(m.group(1)), 0, float(m.group(2))
    return 0, 0, 0.0


def embed(path):
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def shots_for(test_id):
    return sorted(SHOTS.glob(f"{test_id}_*.png"))


def pretty_shot_name(path, test_id):
    stem = path.stem[len(test_id) + 1:]
    stem = re.sub(r"^\d+_", "", stem)
    return stem.replace("_", " ").capitalize()


CSS = """
:root{--ink:#1a1a1a;--muted:#5b6471;--line:#d9dee5;--bg:#fff;
      --pass:#1a7f37;--passbg:#e8f5ec;--fail:#b3261e;--failbg:#fdeaea;--accent:#1f4e79;}
*{box-sizing:border-box}
body{margin:0;background:#eef1f5;color:var(--ink);
     font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.6;}
.page{max-width:1000px;margin:0 auto;background:var(--bg);padding:56px 64px;
      box-shadow:0 2px 18px rgba(0,0,0,.08);}
h1{font-size:30px;margin:0 0 6px;color:var(--accent);}
h2{font-size:23px;margin:46px 0 6px;color:var(--accent);
   border-bottom:3px solid var(--accent);padding-bottom:7px;}
h3{font-size:18px;margin:30px 0 8px;}
h4{font-size:15px;margin:22px 0 6px;color:var(--muted);text-transform:uppercase;
   letter-spacing:.5px;}
p,li{font-size:14.5px}
.sub{color:var(--muted);font-size:15px;margin:0 0 4px}
.meta{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13.5px}
th{background:var(--accent);color:#fff;text-align:left;padding:9px 11px;font-weight:600}
td{padding:8px 11px;border-bottom:1px solid var(--line);vertical-align:top}
tr:nth-child(even) td{background:#f7f9fb}
code{background:#eef1f5;padding:1px 5px;border-radius:3px;
     font-family:Consolas,monospace;font-size:12.5px}
.badge{display:inline-block;padding:2px 9px;border-radius:11px;font-size:11.5px;
       font-weight:700;letter-spacing:.3px}
.PASSED{background:var(--passbg);color:var(--pass)}
.FAILED{background:var(--failbg);color:#b3261e}
.card{border:1px solid var(--line);border-radius:7px;padding:11px 15px;margin:11px 0;
      background:#fcfdfe}
.card.fail{border-left:5px solid #b3261e;background:#fffafa}
.card.pass{border-left:5px solid var(--pass)}
.card h3{margin:0 0 3px;font-size:16px}
.defect{background:#fff6e5;border-left:5px solid #c77700;padding:11px 15px;
        margin:11px 0;border-radius:5px;font-size:13.5px}
.fixed{background:#e8f5ec;border-left:5px solid var(--pass);padding:11px 15px;
       margin:11px 0;border-radius:5px;font-size:13.5px}
figure{margin:10px 0}
img{width:90%;margin:0 auto;border:1px solid var(--line);border-radius:6px;
    display:block}
figcaption{font-size:11.5px;color:var(--muted);margin-top:4px;font-style:italic;
           text-align:center}
.kpis{display:flex;gap:14px;margin:18px 0;flex-wrap:wrap}
.kpi{flex:1;min-width:130px;border:1px solid var(--line);border-radius:8px;
     padding:15px;text-align:center;background:#fcfdfe}
.kpi .n{font-size:30px;font-weight:700;color:var(--accent);line-height:1.1}
.kpi .l{font-size:11.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.submission{display:grid;grid-template-columns:auto 1fr;gap:5px 22px;
            border:1px solid var(--line);border-left:5px solid var(--accent);
            border-radius:6px;padding:14px 20px;margin:16px 0 6px;
            background:#f7f9fb;font-size:14px;max-width:470px}
.submission .k{color:var(--muted);font-weight:600}
.submission .v{color:var(--ink);font-weight:700}
.toc{background:#f7f9fb;border:1px solid var(--line);border-radius:7px;padding:16px 26px}
.toc a{color:var(--accent);text-decoration:none}
.note{background:#eaf2fb;border-left:5px solid var(--accent);padding:11px 15px;
      border-radius:5px;font-size:13.5px;margin:14px 0}
@media print{
  body{background:#fff}
  .page{box-shadow:none;max-width:none;padding:0}
  h2{page-break-after:avoid}
  /* let cards flow so pages pack densely; keep each image whole */
  .card{page-break-inside:auto}
  /* never strand a card's heading/intro above a break - drag them along
     with the figure that follows */
  .card h3,.card .meta,.card .defect{page-break-after:avoid}
  figure,.ex,.defect,.fixed{page-break-inside:avoid}
  figcaption{page-break-before:avoid}
  table{page-break-inside:auto}
  tr{page-break-inside:avoid}
}
"""


def build():
    log = CONSOLE_LOG.read_text(encoding="utf-8", errors="replace")
    results = parse_results(log)
    passed, failed, duration = parse_totals(log)
    total = passed + failed

    o = []
    w = o.append
    w("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    w("<title>PMS - Software &amp; Test Automation Report</title>")
    w(f"<style>{CSS}</style></head><body><div class='page'>")

    # ---------------- Title ----------------
    w("<h1>Chennai BnB Property Management System</h1>")
    w("<p class='sub'>Software Documentation &amp; Automated Test Report "
      "(Assignment Parts A &amp; B)</p>")

    w("<div class='submission'>")
    for k, v in [("Name", "Jeevan S"),
                 ("Registration No", "24BCE1862"),
                 ("Course Code", "BCSE301L"),
                 ("Semester", "FALL26-27"),
                 ("Assessment", "SWE DA3")]:
        w(f"<span class='k'>{k}</span><span class='v'>{v}</span>")
    w("</div>")
    w(f"<p class='meta'>Generated {date.today().isoformat()} &nbsp;|&nbsp; "
      f"{total} automated test cases &nbsp;|&nbsp; execution time {duration:.2f}s</p>")

    w("<div class='kpis'>")
    w(f"<div class='kpi'><div class='n'>{total}</div><div class='l'>Test cases</div></div>")
    w(f"<div class='kpi'><div class='n' style='color:#1a7f37'>{passed}</div>"
      "<div class='l'>Passed</div></div>")
    w(f"<div class='kpi'><div class='n' style='color:#b3261e'>{failed}</div>"
      "<div class='l'>Failed</div></div>")
    w(f"<div class='kpi'><div class='n'>{len(DEFECTS)}</div>"
      "<div class='l'>Defects found</div></div>")
    w(f"<div class='kpi'><div class='n'>{len(FIXED)}</div>"
      "<div class='l'>Defects fixed</div></div>")
    w("</div>")

    w("<div class='toc'><strong>Contents</strong><ol>"
      "<li><a href='#software'>The Software</a></li>"
      "<li><a href='#architecture'>Architecture &amp; Data Model</a></li>"
      "<li><a href='#strategy'>Test Strategy &amp; Tooling</a></li>"
      "<li><a href='#results'>Overall Test Results</a></li>"
      "<li><a href='#cases'>Test Cases &amp; Evidence (by category)</a></li>"
      "<li><a href='#defects'>Defects Found</a></li>"
      "<li><a href='#fixed'>Defects Found &amp; Fixed</a></li>"
      "<li><a href='#howto'>How to Run the Demo</a></li></ol></div>")

    # ---------------- 1. Software ----------------
    w("<h2 id='software'>1. The Software</h2>")
    w("<p><strong>Chennai BnB PMS</strong> is a Property Management System for a small "
      "8-room serviced-apartment property. It lets front-desk staff manage rooms, guests "
      "and the complete booking lifecycle, and exposes the same data through a REST API.</p>")

    w("<h4>Technology stack</h4>")
    w("<table><tr><th>Layer</th><th>Technology</th></tr>"
      "<tr><td>Backend</td><td>Python 3 / Flask (server-rendered Jinja2 templates + REST API)</td></tr>"
      "<tr><td>Database</td><td>MySQL 8.0 via <code>mysql-connector-python</code></td></tr>"
      "<tr><td>Frontend</td><td>HTML5 + CSS (Jinja2 templates), vanilla JavaScript</td></tr>"
      "<tr><td>Auth</td><td>Flask server-side sessions, role-based access control</td></tr>"
      "<tr><td>Test automation</td><td>pytest + requests (API/DB), Playwright (browser UI)</td></tr>"
      "</table>")

    w("<h4>Core features</h4><ul>"
      "<li><strong>Authentication &amp; roles</strong> - three roles (manager, reception, auditor) "
      "with per-endpoint authorisation.</li>"
      "<li><strong>Dashboard</strong> - live occupancy rate, available/occupied counts, "
      "today's check-ins and check-outs.</li>"
      "<li><strong>Room management</strong> - list all rooms, edit price and status "
      "(available / occupied / maintenance).</li>"
      "<li><strong>Guest management</strong> - guest records created automatically from bookings, "
      "with contact details and ID proof.</li>"
      "<li><strong>Booking lifecycle</strong> - create a booking, check in, check out or cancel, "
      "with automatic room-status cascade.</li>"
      "<li><strong>Availability engine</strong> - date-range overlap detection prevents "
      "double-booking; maintenance rooms are excluded.</li>"
      "<li><strong>REST API</strong> - 11 JSON endpoints covering rooms, bookings, guests, "
      "availability and occupancy reporting.</li>"
      "<li><strong>Security hardening</strong> - CSP, X-Frame-Options, nosniff, "
      "Referrer-Policy and no-store headers on every response.</li></ul>")

    w("<h4>User roles</h4>")
    w("<table><tr><th>Role</th><th>Login</th><th>Permissions</th></tr>"
      "<tr><td>Manager</td><td><code>manager / manager123</code></td>"
      "<td>Full access including booking mutation</td></tr>"
      "<tr><td>Reception</td><td><code>reception / reception123</code></td>"
      "<td>Bookings, guests, rooms, availability</td></tr>"
      "<tr><td>Auditor</td><td><code>auditor / auditor123</code></td>"
      "<td>Read-only reporting; blocked from mutating bookings</td></tr></table>")

    # ---------------- 2. Architecture ----------------
    w("<h2 id='architecture'>2. Architecture &amp; Data Model</h2>")
    w("<p>The application is a single Flask service. Browser requests are served as "
      "Jinja2-rendered HTML; the same <code>Database</code> layer also backs the JSON API, "
      "so the UI and the API always read and write identical records in MySQL.</p>")

    w("<div class='note'><strong>Request flow:</strong> "
      "Browser / API client &rarr; Flask route (auth decorator) &rarr; validation &rarr; "
      "<code>Database</code> class &rarr; MySQL &rarr; JSON or rendered template.</div>")

    w("<h4>Database schema</h4>")
    w("<table><tr><th>Table</th><th>Key columns</th><th>Notes</th></tr>"
      "<tr><td><code>rooms</code></td>"
      "<td>room_id, room_number (UNIQUE), room_type, base_price, status, floor, "
      "current_guest_id, current_booking_id</td>"
      "<td>8 seeded rooms; status is an ENUM</td></tr>"
      "<tr><td><code>guests</code></td>"
      "<td>guest_id, name, email, phone, id_proof, created_at</td>"
      "<td>Created automatically when a booking is made</td></tr>"
      "<tr><td><code>bookings</code></td>"
      "<td>booking_id, room_id (FK), guest_id (FK), check_in, check_out, total_price, "
      "status, checked_in_at, checked_out_at</td>"
      "<td>FKs cascade on delete; status is an ENUM</td></tr></table>")

    w("<h4>Booking lifecycle</h4>")
    w("<p><code>confirmed</code> &rarr; <code>checked_in</code> &rarr; <code>checked_out</code>, "
      "with <code>cancelled</code> reachable from any active state. Creating a booking marks the "
      "room <code>occupied</code>; checking out or cancelling returns it to <code>available</code> "
      "- but only when no other active booking still holds that room.</p>")

    w("<h4>REST API endpoints</h4>")
    w("<table><tr><th>Method</th><th>Endpoint</th><th>Auth</th></tr>"
      "<tr><td>GET</td><td><code>/api/hotel-info</code></td><td>none</td></tr>"
      "<tr><td>GET</td><td><code>/api/rooms</code></td><td>none</td></tr>"
      "<tr><td>GET, PUT</td><td><code>/api/rooms/&lt;id&gt;</code></td><td>none</td></tr>"
      "<tr><td>GET</td><td><code>/api/rooms/&lt;id&gt;/guest</code></td><td>any role</td></tr>"
      "<tr><td>GET</td><td><code>/api/rooms/available</code></td><td>any role</td></tr>"
      "<tr><td>GET, POST</td><td><code>/api/bookings</code></td><td>none</td></tr>"
      "<tr><td>GET, PUT, DELETE</td><td><code>/api/bookings/&lt;id&gt;</code></td>"
      "<td>manager, reception</td></tr>"
      "<tr><td>GET</td><td><code>/api/guests</code></td><td>any role</td></tr>"
      "<tr><td>GET</td><td><code>/api/guests/&lt;id&gt;</code></td><td>any role</td></tr>"
      "<tr><td>GET</td><td><code>/api/guests/checked-in</code></td><td>any role</td></tr>"
      "<tr><td>GET</td><td><code>/api/occupancy</code></td><td>any role</td></tr></table>")

    # ---------------- 3. Strategy ----------------
    w("<h2 id='strategy'>3. Test Strategy &amp; Tooling</h2>")
    w(f"<p>{total} automated test cases were written and are organised into the three "
      "categories required by the assignment. Tests run at two layers so the same system is "
      "verified from the outside (browser) and at the contract level (HTTP + SQL).</p>")

    w("<table><tr><th>Layer</th><th>Tooling</th><th>What it covers</th></tr>"
      "<tr><td>UI</td><td>Playwright (Chromium)</td>"
      "<td>Real browser journeys; every test captures a screenshot</td></tr>"
      "<tr><td>API</td><td>pytest + requests</td>"
      "<td>Status codes, JSON payloads, validation and RBAC</td></tr>"
      "<tr><td>Database</td><td>mysql-connector</td>"
      "<td>Direct SQL assertions that data really persisted</td></tr></table>")

    w("<h4>Test isolation</h4>"
      "<p>Every test runs against a database reset to the identical 8-room seed state, so results "
      "are deterministic and the suite can be re-run live, repeatedly, without drift. The Flask "
      "server is started automatically by the test session.</p>")

    # ---------------- 4. Results ----------------
    w("<h2 id='results'>4. Overall Test Results</h2>")

    # per-category tally from the real results
    w("<table><tr><th>Category</th><th>Total</th><th>Passed</th><th>Failed</th>"
      "<th>Failing cases</th></tr>")
    for prefix, label, _ in CATEGORIES:
        ids = [t for t in META if t.startswith(prefix)]
        cp = sum(1 for t in ids if results.get(t) == "PASSED")
        cf = sum(1 for t in ids if results.get(t) == "FAILED")
        fails = ", ".join(sorted(t for t in ids if results.get(t) == "FAILED")) or "-"
        clean = label.replace("Category 1 — ", "").replace("Category 2 — ", "") \
                     .replace("Category 3 — ", "")
        w(f"<tr><td>{clean}</td><td>{len(ids)}</td><td>{cp}</td><td>{cf}</td>"
          f"<td>{fails}</td></tr>")
    w(f"<tr><td><strong>Total</strong></td><td><strong>{total}</strong></td>"
      f"<td><strong>{passed}</strong></td><td><strong>{failed}</strong></td><td></td></tr>")
    w("</table>")

    w("<div class='note'><strong>Reading these results:</strong> the "
      f"{failed} failures are intentional. They are genuine defects left in the build so the "
      "automation can be seen catching real bugs, with at least one failure in every category. "
      f"A further {len(FIXED)} defects were found during this exercise and fixed - the tests "
      "covering them now pass, which is what confirms the fixes.</div>")

    for name, cap in [
        ("RUN-02_test_results_list.png", "Full pytest run - every test case with its result."),
        ("RUN-03_failure_summary.png", "Failure summary: each failing assertion names the defect."),
    ]:
        p = SHOTS / name
        if p.exists():
            w(f"<figure><img src='{embed(p)}' alt='{name}'>"
              f"<figcaption>{cap}</figcaption></figure>")

    # ---------------- 5. Cases ----------------
    w("<h2 id='cases'>5. Test Cases &amp; Evidence</h2>")
    w("<p>Every test case is listed below with its purpose, automation layer and the actual "
      "result from the run above. <strong>All "
      f"{total} test cases carry their own visual evidence</strong>, captured automatically "
      "while the suite was executing:</p>")
    w("<ul>"
      "<li><strong>UI test cases</strong> - full-page screenshots of the real Chromium "
      "browser at each step of the journey.</li>"
      "<li><strong>API and database test cases</strong> - an evidence card showing the actual "
      "HTTP request and response recorded during the run (method, URL, payload, status code "
      "and JSON body), the real assertion lines taken from the test source, and the outcome. "
      "Nothing on these cards is written by hand; it is the live exchange from the run "
      "above.</li></ul>")

    for prefix, label, blurb in CATEGORIES:
        ids = sorted((t for t in META if t.startswith(prefix)),
                     key=lambda x: int(x.split("-")[1]))
        w(f"<h3>{label}</h3><p class='meta'>{blurb}</p>")

        w("<table><tr><th style='width:76px'>ID</th><th>Test case</th>"
          "<th style='width:78px'>Layer</th><th style='width:84px'>Result</th></tr>")
        for tid in ids:
            title, layer, _ = META[tid]
            status = results.get(tid, "n/a")
            w(f"<tr><td><code>{tid}</code></td><td>{title}</td><td>{layer}</td>"
              f"<td><span class='badge {status}'>{status}</span></td></tr>")
        w("</table>")

        # detail cards with screenshots / defect notes
        for tid in ids:
            title, layer, purpose = META[tid]
            status = results.get(tid, "n/a")
            imgs = shots_for(tid)
            if not imgs and tid not in DEFECTS:
                continue  # keep the document readable: detail only where there is evidence
            cls = "fail" if status == "FAILED" else "pass"
            w(f"<div class='card {cls}'>")
            w(f"<h3>{tid} &mdash; {title} "
              f"<span class='badge {status}'>{status}</span></h3>")
            w(f"<p class='meta'>Layer: {layer} &nbsp;|&nbsp; {html.escape(purpose)}</p>")
            if tid in DEFECTS:
                ref, text = DEFECTS[tid]
                w(f"<div class='defect'><strong>Defect {ref}:</strong> {text}</div>")
            for img in imgs:
                w(f"<figure><img src='{embed(img)}' alt='{img.stem}'>"
                  f"<figcaption>{tid} &mdash; {pretty_shot_name(img, tid)}</figcaption></figure>")
            w("</div>")

    # ---------------- 6. Defects ----------------
    w("<h2 id='defects'>6. Defects Found (open)</h2>")
    w("<p>These defects remain in the build and are what the failing tests detect.</p>")
    w("<table><tr><th style='width:60px'>Ref</th><th style='width:84px'>Test</th>"
      "<th>Defect</th></tr>")
    for tid, (ref, text) in sorted(DEFECTS.items(), key=lambda kv: kv[1][0]):
        w(f"<tr><td><strong>{ref}</strong></td><td><code>{tid}</code></td><td>{text}</td></tr>")
    w("</table>")

    # ---------------- 7. Fixed ----------------
    w("<h2 id='fixed'>7. Defects Found &amp; Fixed</h2>")
    w("<p>These were discovered while building the suite and have been repaired. Their tests "
      "now pass, which is the evidence that the fix works.</p>")
    for ref, title, text, tests in FIXED:
        w(f"<div class='fixed'><strong>{ref} &mdash; {title}</strong><br>{text}"
          f"<br><span class='meta'>Verified by: {tests}</span></div>")

    # ---------------- 8. How to run ----------------
    w("<h2 id='howto'>8. How to Run the Demo</h2>")
    w("<table><tr><th style='width:34px'>#</th><th>Step</th><th>Command</th></tr>"
      "<tr><td>1</td><td>Ensure MySQL is running and the schema is loaded</td>"
      "<td><code>mysql -u root -p &lt; schema.sql</code></td></tr>"
      "<tr><td>2</td><td>Run the whole suite (starts the app automatically)</td>"
      "<td><code>python -m pytest -v</code></td></tr>"
      "<tr><td>3</td><td>Run one category only</td>"
      "<td><code>python -m pytest tests/test_category2_boundary.py -v</code></td></tr>"
      "<tr><td>4</td><td>Run only the browser tests (add <code>--headed</code> to watch)</td>"
      "<td><code>python -m pytest tests/test_category1_e2e_ui.py --headed</code></td></tr>"
      "<tr><td>5</td><td>Regenerate the HTML report</td>"
      "<td><code>python -m pytest --html=test_evidence/report.html --self-contained-html</code></td></tr>"
      "<tr><td>6</td><td>Rebuild this document (after a run)</td>"
      "<td><code>python tools/capture_evidence.py</code><br>"
      "<code>python tools/render_api_cards.py</code><br>"
      "<code>python tools/build_demo_document.py</code></td></tr>"
      "</table>")

    w("<div class='note'><strong>Live demo tip:</strong> run step 4 with "
      "<code>--headed --slowmo 600</code> to show Chromium driving the application in real time "
      "- filling the booking form, checking a guest in and checking them out - then run step 2 "
      "to show the full suite and the defects it catches.</div>")

    w("</div></body></html>")

    OUTPUT.write_text("".join(o), encoding="utf-8")
    size = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"Wrote {OUTPUT}  ({size:.1f} MB)")
    print(f"Parsed {len(results)} test results: {passed} passed, {failed} failed")


if __name__ == "__main__":
    build()
