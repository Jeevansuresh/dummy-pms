"""
Shared pytest fixtures for the Chennai BnB PMS automated test suite.

Provides:
  * a live Flask server started on a dedicated test port
  * a database reset to the known 8-room seed state before every test
  * pre-authenticated requests.Session objects for each role
  * a screenshots directory for UI evidence capture
"""
import os
import pathlib
import subprocess
import sys
import time
from datetime import date, timedelta

import inspect
import json
import re

import mysql.connector
import pytest
import requests

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("PMS_TEST_PORT", "5055"))
BASE_URL = f"http://127.0.0.1:{PORT}"

EVIDENCE_DIR = BASE_DIR / "test_evidence"
SHOTS_DIR = EVIDENCE_DIR / "screenshots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BASE_DIR))
try:
    # local, git-ignored credentials (see db_config.example.py)
    from db_config import DB_PASSWORD as _LOCAL_DB_PASSWORD
except ImportError:
    _LOCAL_DB_PASSWORD = ""

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", _LOCAL_DB_PASSWORD),
    "database": os.environ.get("DB_NAME", "dummy_pms"),
}

# Seed prices from schema.sql — restored before each test
SEED_ROOMS = {
    1: ("101", 3500.00), 2: ("102", 3500.00),
    3: ("103", 4500.00), 4: ("104", 4500.00),
    5: ("105", 6000.00), 6: ("106", 6000.00),
    7: ("107", 7500.00), 8: ("108", 7500.00),
}

CREDENTIALS = {
    "manager": ("manager", "manager123"),
    "reception": ("reception", "reception123"),
    "auditor": ("auditor", "auditor123"),
}


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------
def db_connect():
    return mysql.connector.connect(**DB_CONFIG)


def _kill_stale_connections(cur):
    """
    Drop any idle connections left behind on the test database.

    A leaked connection sitting in an open transaction holds metadata locks and
    would make the TRUNCATE below block indefinitely, so the suite clears them
    before resetting. Safe here because the app opens a fresh connection per query.
    """
    cur.execute("SELECT CONNECTION_ID()")
    own_id = cur.fetchone()[0]
    cur.execute(
        """SELECT id FROM information_schema.processlist
           WHERE db = %s AND id <> %s AND command = 'Sleep'""",
        (DB_CONFIG["database"], own_id),
    )
    for (pid,) in cur.fetchall():
        try:
            cur.execute(f"KILL {int(pid)}")
        except mysql.connector.Error:
            pass  # connection already gone


def reset_database():
    """Return the DB to the known seed state: 8 available rooms, no guests/bookings."""
    conn = db_connect()
    cur = conn.cursor()
    # fail fast instead of hanging if something still holds a lock
    cur.execute("SET SESSION innodb_lock_wait_timeout = 10")
    _kill_stale_connections(cur)
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    cur.execute("TRUNCATE TABLE bookings")
    cur.execute("TRUNCATE TABLE guests")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    for room_id, (number, price) in SEED_ROOMS.items():
        cur.execute(
            """UPDATE rooms
               SET room_number=%s, base_price=%s, status='available',
                   current_guest_id=NULL, current_booking_id=NULL
               WHERE room_id=%s""",
            (number, price, room_id),
        )
    conn.commit()
    cur.close()
    conn.close()


def query_one(sql, params=()):
    conn = db_connect()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def query_all(sql, params=()):
    conn = db_connect()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# --------------------------------------------------------------------------
# Date helpers — always use future dates so bookings never collide with "today"
# --------------------------------------------------------------------------
def day(offset):
    """Return an ISO date string `offset` days from today."""
    return (date.today() + timedelta(days=offset)).isoformat()


# --------------------------------------------------------------------------
# Live server
# --------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def live_server():
    """Start app.py on the test port for the whole session."""
    env = os.environ.copy()
    env["PORT"] = str(PORT)
    # development mode keeps SESSION_COOKIE_SECURE off so sessions work over http
    env["FLASK_ENV"] = "development"
    env.setdefault("DB_PASSWORD", DB_CONFIG["password"])

    # Stream the server log to a file rather than a PIPE: an undrained pipe fills
    # at ~64KB of request logging and deadlocks the whole suite.
    log_path = EVIDENCE_DIR / "server.log"
    log_file = open(log_path, "w", encoding="utf-8")

    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=str(BASE_DIR),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    deadline = time.time() + 40
    while time.time() < deadline:
        if proc.poll() is not None:
            log_file.close()
            raise RuntimeError(
                f"App failed to start:\n{log_path.read_text(encoding='utf-8', errors='replace')}"
            )
        try:
            requests.get(BASE_URL + "/", timeout=1)
            break
        except requests.exceptions.RequestException:
            time.sleep(0.4)
    else:
        proc.terminate()
        log_file.close()
        raise RuntimeError("App did not become ready within 40s")

    yield BASE_URL

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log_file.close()


@pytest.fixture(autouse=True)
def clean_db(live_server):
    """Reset the database to seed state before every single test."""
    reset_database()
    yield


# --------------------------------------------------------------------------
# HTTP exchange recorder
#
# Captures the real request/response of every API call made during a test body,
# so each test can be rendered as a visual evidence card for the demo document.
# --------------------------------------------------------------------------
EXCHANGE_FILE = EVIDENCE_DIR / "api_exchanges.json"
_RECORDS = {}
_CURRENT = {"id": None}

MAX_BODY_CHARS = 900


def _test_id(name):
    """test_BND_11_double_booking... -> 'BND-11'"""
    m = re.match(r"test_([A-Z0-9]+)_(\d+)_", name)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _shorten(text):
    if text is None:
        return None
    text = str(text)
    return text if len(text) <= MAX_BODY_CHARS else text[:MAX_BODY_CHARS] + "\n... (truncated)"


def _pretty_json(raw):
    """Pretty-print a JSON body; fall back to the raw text when it is HTML."""
    try:
        return json.dumps(json.loads(raw), indent=2)[:MAX_BODY_CHARS]
    except Exception:
        return None


def _record_exchange(resp, *args, **kwargs):
    """requests response hook - runs for every HTTP call inside a test body."""
    tid = _CURRENT["id"]
    if tid is None:
        return
    req = resp.request

    body = req.body
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")

    pretty_resp = _pretty_json(resp.text)
    if pretty_resp is None:
        # an HTML page - just note what it was rather than dumping markup
        title = re.search(r"<title>(.*?)</title>", resp.text, re.I | re.S)
        pretty_resp = (f"[HTML page: {title.group(1).strip()}]" if title
                       else f"[HTML response, {len(resp.text)} chars]")

    _RECORDS.setdefault(tid, {"exchanges": []})["exchanges"].append({
        "method": req.method,
        "url": req.url.replace(BASE_URL, ""),
        "request_body": _shorten(_pretty_json(body) or body),
        "status": resp.status_code,
        "reason": resp.reason,
        "response_body": _shorten(pretty_resp),
    })


def _attach_recorder(session):
    session.hooks.setdefault("response", []).append(_record_exchange)
    return session


# Only record during the test body, not during fixture setup/teardown,
# so helper logins do not clutter each card.
@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    _CURRENT["id"] = None


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item):
    tid = _test_id(item.name)
    _CURRENT["id"] = tid
    if tid:
        _RECORDS.setdefault(tid, {"exchanges": []})


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    _CURRENT["id"] = None


def pytest_runtest_makereport(item, call):
    """Attach the outcome, purpose and real assertion lines to each record."""
    if call.when != "call":
        return
    tid = _test_id(item.name)
    if not tid:
        return
    rec = _RECORDS.setdefault(tid, {"exchanges": []})

    rec["outcome"] = "PASSED" if call.excinfo is None else "FAILED"
    rec["purpose"] = inspect.cleandoc(item.function.__doc__ or "").strip()

    try:
        source = inspect.getsource(item.function)
        rec["assertions"] = [
            line.strip() for line in source.splitlines()
            if line.strip().startswith("assert ")
        ]
    except OSError:
        rec["assertions"] = []

    if call.excinfo is not None:
        rec["error"] = _shorten(str(call.excinfo.value).split("\nassert")[0].strip())


def pytest_sessionfinish(session, exitstatus):
    if _RECORDS:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        EXCHANGE_FILE.write_text(json.dumps(_RECORDS, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# HTTP sessions
# --------------------------------------------------------------------------
@pytest.fixture
def anon():
    """Unauthenticated HTTP session."""
    with requests.Session() as s:
        yield _attach_recorder(s)


def login_session(role):
    """Return a requests.Session authenticated as the given role."""
    username, password = CREDENTIALS[role]
    s = requests.Session()
    resp = s.post(
        f"{BASE_URL}/login",
        data={"username": username, "password": password},
        allow_redirects=False,
        timeout=10,
    )
    assert resp.status_code in (301, 302), f"login as {role} failed: {resp.status_code}"
    return _attach_recorder(s)


@pytest.fixture
def manager():
    s = login_session("manager")
    yield s
    s.close()


@pytest.fixture
def reception():
    s = login_session("reception")
    yield s
    s.close()


@pytest.fixture
def auditor():
    s = login_session("auditor")
    yield s
    s.close()


# --------------------------------------------------------------------------
# Convenience builders
# --------------------------------------------------------------------------
def booking_payload(room_id=1, nights_from=1, nights_to=3, **overrides):
    payload = {
        "room_id": room_id,
        "guest_name": "Test Guest",
        "guest_email": "test.guest@example.com",
        "guest_phone": "9876543210",
        "check_in": day(nights_from),
        "check_out": day(nights_to),
    }
    payload.update(overrides)
    return payload


def create_booking_api(session, **overrides):
    """Create a booking through the API and return the parsed JSON body."""
    resp = session.post(f"{BASE_URL}/api/bookings", json=booking_payload(**overrides), timeout=10)
    return resp


# --------------------------------------------------------------------------
# UI / Playwright support
# --------------------------------------------------------------------------
@pytest.fixture
def shots():
    """Directory where UI screenshots are written."""
    return SHOTS_DIR


@pytest.fixture
def ui_login(page):
    """Log the browser session in as the given role and return the page."""
    def _login(role="manager"):
        username, password = CREDENTIALS[role]
        page.goto(f"{BASE_URL}/login")
        page.fill("input[name='username']", username)
        page.fill("input[name='password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_load_state("networkidle")
        return page
    return _login
