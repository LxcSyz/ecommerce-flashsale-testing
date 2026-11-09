"""Run as python -m scripts.capture_preview after installing Chromium."""
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.server import create_server


def main():
    with tempfile.TemporaryDirectory(prefix="tradelab-preview-") as directory:
        server = create_server("127.0.0.1", 0, Path(directory) / "preview.db")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                page.locator(".product").first.wait_for()
                Path("docs/assets").mkdir(parents=True, exist_ok=True)
                page.screenshot(path="docs/assets/tradelab.png", full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile overflow"
                Path("reports").mkdir(exist_ok=True)
                page.screenshot(path="reports/mobile-preview.png", full_page=True)
                assert not errors, errors
                browser.close()
                print("Desktop/mobile screenshots captured; no JS exceptions or mobile horizontal overflow.")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
