import os
import random
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from app.config import settings

os.makedirs("logs/screenshots", exist_ok=True)


class LinkedInCheckpointError(Exception):
    """Raised when LinkedIn triggers a login wall, CAPTCHA, or account restriction."""
    pass


def _save_debug_screenshot(page, tag: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    page.screenshot(path=f"logs/screenshots/{tag}_{ts}.png")


def _first_visible(page, selectors: list[str], timeout: int = 6000):
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except PlaywrightTimeoutError:
            continue
    return None


def _get_browser_context(p, li_at_cookie: str, proxy_url: str | None = None):
    launch_args = {"headless": settings.PLAYWRIGHT_HEADLESS}
    if proxy_url:
        launch_args["proxy"] = {"server": proxy_url}

    browser = p.chromium.launch(**launch_args)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
    )
    context.add_cookies([{
        "name": "li_at",
        "value": li_at_cookie,
        "domain": ".www.linkedin.com",
        "path": "/",
        "httpOnly": True,
        "secure": True,
    }])
    return browser, context


def _try_connect_with_note(page, message_text: str) -> bool:
    """Fallback for 2nd/3rd-degree profiles: sends a connection request with a note (<= 300 chars)."""
    connect_btn = _first_visible(page, [
        "main button:has-text('Connect')",
        "button[aria-label^='Invite'][aria-label*='connect']",
    ], timeout=4000)

    # Sometimes 'Connect' is hidden inside the 'More' dropdown
    if not connect_btn:
        more_btn = _first_visible(page, ["main button:has-text('More')"], timeout=3000)
        if more_btn:
            more_btn.click()
            time.sleep(random.uniform(1.0, 2.0))
            connect_btn = _first_visible(page, [
                "div[role='button']:has-text('Connect')",
                "span:has-text('Connect')",
            ], timeout=3000)

    if not connect_btn:
        return False

    connect_btn.click()
    time.sleep(random.uniform(1.5, 2.5))

    add_note_btn = _first_visible(page, ["button:has-text('Add a note')"], timeout=4000)
    if not add_note_btn:
        return False

    add_note_btn.click()
    time.sleep(random.uniform(1.0, 2.0))

    note_box = _first_visible(page, ["textarea[name='message']", "textarea#custom-message"], timeout=4000)
    if not note_box:
        return False

    # LinkedIn strictly caps connection notes at 300 characters
    short_note = message_text[:290].rsplit(" ", 1)[0] + "..." if len(message_text) > 290 else message_text
    note_box.type(short_note, delay=random.randint(35, 75))
    time.sleep(random.uniform(1.0, 2.0))

    send_invite_btn = _first_visible(page, ["button:has-text('Send')"], timeout=4000)
    if not send_invite_btn:
        return False

    send_invite_btn.click()
    time.sleep(random.uniform(2.0, 3.5))
    return True


def send_message_playwright(
    li_at_cookie: str,
    profile_url: str,
    message_text: str,
    proxy_url: str | None = None,
) -> str:
    """
    Sends a DM if 1st-degree connected.
    Falls back to 'Connect + Add a note' if Message is locked behind InMail.
    Returns 'SENT_DM' or 'SENT_CONNECT_NOTE'.
    """
    with sync_playwright() as p:
        browser, context = _get_browser_context(p, li_at_cookie, proxy_url)
        page = context.new_page()
        try:
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(3.0, 6.0))

            if "login" in page.url or "checkpoint" in page.url:
                _save_debug_screenshot(page, "checkpoint_send")
                raise LinkedInCheckpointError("Session expired or checkpoint triggered.")

            # Try direct Message button first
            msg_btn = _first_visible(page, [
                "main button:has-text('Message')",
                "a[href*='/messaging/compose']",
            ], timeout=5000)

            if msg_btn:
                msg_btn.click()
                time.sleep(random.uniform(1.5, 3.0))

                # Check if clicking Message opened a normal chat box (not an InMail upsell modal)
                input_box = _first_visible(page, [
                    "div.msg-form__contenteditable[role='textbox']",
                    "div[role='textbox'][aria-label*='Write a message']",
                ], timeout=5000)

                if input_box:
                    input_box.click()
                    input_box.type(message_text, delay=random.randint(35, 85))
                    time.sleep(random.uniform(1.0, 2.5))

                    send_btn = _first_visible(page, [
                        "button.msg-form__send-button[type='submit']",
                        "button[type='submit']:has-text('Send')",