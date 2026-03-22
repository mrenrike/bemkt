"""
Standalone script: render an HTML file to PNG via Playwright.
Usage: python render_slide.py <html_path> <png_path>
Run as a subprocess from carousel.py to avoid asyncio event loop conflicts on Windows.
"""
import sys

def main():
    html_path = sys.argv[1]
    png_path  = sys.argv[2]

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--disable-web-security",
            "--allow-file-access-from-files",
            "--disable-features=IsolateOrigins,site-per-process",
        ])
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.goto(f"file:///{html_path.replace(chr(92), '/')}")
        try:
            page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            pass
        try:
            page.evaluate("() => document.fonts.ready")
        except Exception:
            pass
        page.wait_for_timeout(400)
        page.screenshot(path=png_path, full_page=False)
        browser.close()

if __name__ == "__main__":
    main()
