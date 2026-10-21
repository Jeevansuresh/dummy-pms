"""
Capture Part B demo evidence as screenshots.

Renders the real pytest console output and the pytest HTML report into PNG
images under test_evidence/screenshots/ so they can be embedded in the demo
document.

Usage (after running the suite):
    python tools/capture_evidence.py
"""
import html
import pathlib
import re
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "test_evidence"
SHOTS = EVIDENCE / "screenshots"
CONSOLE_LOG = EVIDENCE / "console_output.txt"
HTML_REPORT = EVIDENCE / "report.html"

SHOTS.mkdir(parents=True, exist_ok=True)

TERMINAL_CSS = """
  body { margin:0; background:#0d1117; }
  pre {
    margin:0; padding:28px 32px;
    background:#0d1117; color:#c9d1d9;
    font-family: 'Cascadia Code','Consolas','DejaVu Sans Mono',monospace;
    font-size:13.5px; line-height:1.55;
    white-space:pre-wrap; word-break:break-word;
  }
  .pass   { color:#3fb950; font-weight:600; }
  .fail   { color:#f85149; font-weight:700; }
  .head   { color:#58a6ff; font-weight:700; }
  .okline { color:#3fb950; font-weight:700; }
  .badline{ color:#f85149; font-weight:700; }
  .dim    { color:#8b949e; }
"""


def colorize(raw: str) -> str:
    """HTML-escape the log then apply terminal-style colouring."""
    out = html.escape(raw)
    out = out.replace("PASSED", '<span class="pass">PASSED</span>')
    out = re.sub(r"\bFAILED\b", '<span class="fail">FAILED</span>', out)
    out = re.sub(r"^(=+ test session starts =+)$", r'<span class="head">\1</span>',
                 out, flags=re.M)
    out = re.sub(r"^(=+ FAILURES =+)$", r'<span class="badline">\1</span>', out, flags=re.M)
    out = re.sub(r"^(=+ short test summary info =+)$", r'<span class="head">\1</span>',
                 out, flags=re.M)
    out = re.sub(r"^(=+ \d+ failed, \d+ passed.*)$", r'<span class="badline">\1</span>',
                 out, flags=re.M)
    out = re.sub(r"^(=+ \d+ passed.*)$", r'<span class="okline">\1</span>', out, flags=re.M)
    return out


def terminal_page(raw: str) -> str:
    return f"<!doctype html><meta charset='utf-8'><style>{TERMINAL_CSS}</style>" \
           f"<pre>{colorize(raw)}</pre>"


MAX_SHOT_HEIGHT = 15000  # Chromium refuses to rasterise much beyond this


def safe_shot(page, path, label):
    """
    Screenshot a page, falling back to a clipped capture when the content is
    taller than Chromium can rasterise in one go.
    """
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"captured {path.name}")
        return True
    except Exception:
        try:
            height = min(page.evaluate("document.body.scrollHeight"), MAX_SHOT_HEIGHT)
            page.screenshot(
                path=str(path),
                clip={"x": 0, "y": 0, "width": 1280, "height": height},
            )
            print(f"captured {path.name} (clipped to {height}px - content too tall)")
            return True
        except Exception as exc:
            print(f"skipped {label}: {exc}")
            return False


def main():
    if not CONSOLE_LOG.exists():
        sys.exit(f"Missing {CONSOLE_LOG}. Run the test suite first (see README).")

    raw = CONSOLE_LOG.read_text(encoding="utf-8", errors="replace")

    # Split the log into the per-test result list and the failure detail tail
    marker = "=========================== short test summary info"
    if marker in raw:
        results_part, summary_part = raw.split(marker, 1)
        summary_part = marker + summary_part
    else:
        results_part, summary_part = raw, ""

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # 1. full console output (optional - can be very tall)
        page.set_content(terminal_page(raw))
        safe_shot(page, SHOTS / "RUN-01_full_console_output.png", "full console output")

        # 2. per-test results only
        page.set_content(terminal_page(results_part))
        safe_shot(page, SHOTS / "RUN-02_test_results_list.png", "test results list")

        # 3. failure summary only
        if summary_part:
            page.set_content(terminal_page(summary_part))
            safe_shot(page, SHOTS / "RUN-03_failure_summary.png", "failure summary")

        # 4. the pytest HTML report
        if HTML_REPORT.exists():
            page.goto(HTML_REPORT.as_uri())
            page.wait_for_load_state("networkidle")
            safe_shot(page, SHOTS / "RUN-04_html_report.png", "html report")

        browser.close()

    print(f"\nAll evidence written to {SHOTS}")


if __name__ == "__main__":
    main()
