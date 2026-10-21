"""
Render one API evidence card per test case.

Reads test_evidence/api_exchanges.json - the real HTTP request/response pairs
captured while the suite was running - and renders each test as a PNG card
showing the actual exchange, the real assertion lines from the test source and
the outcome.

UI tests are skipped: they already have genuine browser screenshots.

Usage:
    python tools/render_api_cards.py
"""
import html
import json
import pathlib
import re
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_demo_document import META  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "test_evidence"
SHOTS = EVIDENCE / "screenshots"
EXCHANGES = EVIDENCE / "api_exchanges.json"

# A card must fit inside one printed page. The document shows a 900px-wide card
# at roughly 700px, so anything over ~1300px native overflows the A4 text area
# and gets pushed to the next page, leaving a blank gap behind it.
MAX_CARD_PX = 1150

# Progressively tighter (max_exchanges, body_chars) settings, tried in order
# until the rendered card fits.
TRIM_STEPS = [(3, 430), (2, 350), (2, 220), (1, 220)]


def compact(text, limit):
    """
    Re-format a recorded JSON body compactly: flat arrays collapse onto one
    line and the body is capped, so an evidence card stays readable on one
    printed page. Values are never altered.
    """
    if not text:
        return text
    try:
        pretty = json.dumps(json.loads(text), indent=2)
    except Exception:
        pretty = text
    # collapse arrays of scalars (e.g. amenities) onto a single line
    pretty = re.sub(
        r"\[\s+((?:[^\[\]{}])*?)\s+\]",
        lambda m: "[" + " ".join(m.group(1).split()) + "]",
        pretty,
    )
    if len(pretty) > limit:
        pretty = pretty[:limit].rstrip() + "\n... (truncated)"
    return pretty

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#fff;font-family:'Segoe UI',Roboto,Arial,sans-serif;}
.card{width:900px;padding:15px 20px;}
.hdr{display:flex;align-items:center;gap:12px;border-bottom:3px solid #1f4e79;
     padding-bottom:8px;margin-bottom:4px}
.tid{font-family:Consolas,monospace;font-size:17px;font-weight:700;color:#1f4e79}
.title{font-size:15px;font-weight:600;flex:1}
.badge{padding:3px 11px;border-radius:12px;font-size:11px;font-weight:700;
       letter-spacing:.4px}
.PASSED{background:#e8f5ec;color:#1a7f37}
.FAILED{background:#fdeaea;color:#b3261e}
.purpose{color:#5b6471;font-size:12px;margin:6px 0 10px;font-style:italic}
h4{font-size:10px;text-transform:uppercase;letter-spacing:.9px;color:#5b6471;
   margin:10px 0 4px;font-weight:700}
.ex{border:1px solid #d9dee5;border-radius:6px;margin-bottom:8px;overflow:hidden}
.ex-hd{background:#f2f5f8;padding:5px 11px;font-family:Consolas,monospace;
       font-size:12px;font-weight:700;display:flex;justify-content:space-between;
       align-items:center;border-bottom:1px solid #d9dee5}
.method{color:#1f4e79}
.st{padding:2px 10px;border-radius:10px;font-size:12px}
.s2{background:#e8f5ec;color:#1a7f37}
.s4{background:#fff4e5;color:#b86e00}
.s5{background:#fdeaea;color:#b3261e}
.s3{background:#eaf2fb;color:#1f4e79}
.body{padding:6px 11px;border-top:1px solid #eef1f5}
.lbl{font-size:9.5px;color:#8b949e;text-transform:uppercase;letter-spacing:.7px;
     margin-bottom:2px;font-weight:700}
pre{margin:0;font-family:Consolas,'DejaVu Sans Mono',monospace;font-size:11px;
    line-height:1.35;white-space:pre-wrap;word-break:break-word;color:#24292f}
.asserts{background:#f7f9fb;border-left:4px solid #1f4e79;border-radius:4px;
         padding:7px 11px}
.asserts pre{font-size:10.5px;color:#1a1a1a}
.err{background:#fdeaea;border-left:4px solid #b3261e;border-radius:4px;
     padding:7px 11px;margin-top:7px}
.err pre{font-size:10.5px;color:#8c1d18}
.none{color:#8b949e;font-size:12.5px;font-style:italic}
"""


def status_class(code):
    return {2: "s2", 3: "s3", 4: "s4", 5: "s5"}.get(code // 100, "s4")


def card_html(tid, rec, max_exchanges=3, body_limit=430):
    title, layer, _purpose = META.get(tid, (tid, "", ""))
    outcome = rec.get("outcome", "n/a")
    purpose = rec.get("purpose") or _purpose

    o = [f"<style>{CSS}</style><div class='card'>"]
    o.append("<div class='hdr'>"
             f"<span class='tid'>{tid}</span>"
             f"<span class='title'>{html.escape(title)}</span>"
             f"<span class='badge {outcome}'>{outcome}</span></div>")
    o.append(f"<div class='purpose'>{html.escape(purpose)}</div>")

    exchanges = rec.get("exchanges", [])[:max_exchanges]
    if exchanges:
        o.append(f"<h4>HTTP exchange{'s' if len(exchanges) > 1 else ''} "
                 f"captured during the run</h4>")
        for ex in exchanges:
            o.append("<div class='ex'><div class='ex-hd'>"
                     f"<span><span class='method'>{ex['method']}</span> "
                     f"{html.escape(ex['url'])}</span>"
                     f"<span class='st {status_class(ex['status'])}'>"
                     f"{ex['status']} {ex['reason']}</span></div>")
            if ex.get("request_body"):
                o.append("<div class='body'><div class='lbl'>Request body</div>"
                         f"<pre>{html.escape(compact(ex['request_body'], body_limit))}"
                         "</pre></div>")
            if ex.get("response_body"):
                o.append("<div class='body'><div class='lbl'>Response</div>"
                         f"<pre>{html.escape(compact(ex['response_body'], body_limit))}"
                         "</pre></div>")
            o.append("</div>")
    else:
        o.append("<h4>Verification method</h4>"
                 "<p class='none'>No HTTP call - this test asserts directly against "
                 "the MySQL database.</p>")

    asserts = rec.get("assertions", [])
    if asserts:
        o.append("<h4>Assertions executed (from the test source)</h4>")
        o.append("<div class='asserts'><pre>"
                 + html.escape("\n".join(asserts)) + "</pre></div>")

    if rec.get("error"):
        o.append("<h4>Failure detail</h4>"
                 f"<div class='err'><pre>{html.escape(rec['error'])}</pre></div>")

    o.append("</div>")
    return "".join(o)


def main():
    if not EXCHANGES.exists():
        sys.exit(f"Missing {EXCHANGES}. Run the test suite first.")

    records = json.loads(EXCHANGES.read_text(encoding="utf-8"))
    SHOTS.mkdir(parents=True, exist_ok=True)

    # Tests that already have real browser screenshots need no card.
    # Cards this script generated must be excluded, or a re-run would treat its
    # own previous output as browser evidence and skip those tests.
    has_browser_shot = {
        p.stem.split("_")[0] for p in SHOTS.glob("*.png")
        if not p.stem.endswith("_api_evidence")
    }

    made = skipped = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # scale 1: the cards are displayed at roughly their native width in the
        # document, so rendering at 2x only quadruples the file size
        # A short viewport matters: full_page screenshots are never smaller than
        # the viewport, so a tall one pads every short card with blank space.
        page = browser.new_page(viewport={"width": 900, "height": 200},
                                device_scale_factor=1)
        trimmed = []
        for tid in sorted(records, key=lambda t: (t.split("-")[0], int(t.split("-")[1]))):
            if tid in has_browser_shot:
                skipped += 1
                continue

            # Render progressively tighter until the card fits on one printed
            # page. An oversized figure cannot be split, so it would otherwise
            # be pushed to the next page and leave a blank gap behind it.
            for step, (max_ex, limit) in enumerate(TRIM_STEPS):
                page.set_content(card_html(tid, records[tid], max_ex, limit))
                height = page.evaluate("document.body.scrollHeight")
                if height <= MAX_CARD_PX:
                    break
            if step:
                trimmed.append(f"{tid}({height}px)")

            page.screenshot(path=str(SHOTS / f"{tid}_api_evidence.png"), full_page=True)
            made += 1
        browser.close()

    print(f"Rendered {made} API evidence cards "
          f"({skipped} skipped - they have browser screenshots)")
    if trimmed:
        print(f"  trimmed to fit one page: {', '.join(trimmed)}")
    print(f"Written to {SHOTS}")


if __name__ == "__main__":
    main()
