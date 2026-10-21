"""
Export the demo document to PDF.

Renders test_evidence/DEMO_DOCUMENT.html through headless Chromium and writes
an A4 PDF with page numbers, suitable for submission or printing.

Usage:
    python tools/export_pdf.py
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "test_evidence"
SOURCE = EVIDENCE / "DEMO_DOCUMENT.html"
OUTPUT = EVIDENCE / "DEMO_DOCUMENT.pdf"

FOOTER = """
<div style="width:100%;font-size:8px;color:#777;padding:0 14mm;
            font-family:Segoe UI,Arial,sans-serif;display:flex;
            justify-content:space-between;">
  <span>Jeevan S &middot; 24BCE1862 &middot; BCSE301L SWE DA3 &mdash; Chennai BnB PMS</span>
  <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
</div>
"""

EMPTY_HEADER = "<div></div>"


def main():
    if not SOURCE.exists():
        sys.exit(f"Missing {SOURCE}. Run tools/build_demo_document.py first.")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(SOURCE.as_uri())
        page.wait_for_load_state("networkidle")

        # make sure every embedded image has decoded before printing
        page.evaluate("""() => Promise.all(
            [...document.images]
              .filter(i => !i.complete)
              .map(i => new Promise(r => { i.onload = i.onerror = r; }))
        )""")

        broken = page.evaluate(
            "[...document.images].filter(i=>!i.complete||i.naturalWidth===0).length")
        if broken:
            print(f"warning: {broken} image(s) failed to load")

        page.pdf(
            path=str(OUTPUT),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template=EMPTY_HEADER,
            footer_template=FOOTER,
            margin={"top": "12mm", "bottom": "14mm", "left": "10mm", "right": "10mm"},
        )
        browser.close()

    size = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"Wrote {OUTPUT}  ({size:.1f} MB)")


if __name__ == "__main__":
    main()
