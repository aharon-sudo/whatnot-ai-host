"""One-time interactive Whatnot login.

Opens a real Chromium window, lets you log in by hand (including any 2FA),
then saves the authenticated session to WHATNOT_STORAGE_STATE_PATH so the
bot can reuse it without logging in again.

Run: python scripts/login_whatnot.py
"""

from playwright.sync_api import sync_playwright

from config.settings import load_settings


def main() -> None:
    settings = load_settings()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.whatnot.com/login")

        input(
            "Log in to your Whatnot seller account in the opened browser window, "
            "navigate to your seller dashboard, then press Enter here to save the session..."
        )

        context.storage_state(path=settings.whatnot_storage_state_path)
        print(f"Saved session to {settings.whatnot_storage_state_path}")
        browser.close()


if __name__ == "__main__":
    main()
