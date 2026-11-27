import os
import random
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

os.makedirs("logs/screenshots", exist_ok=True)

class LinkedInCheckpointError(Exception):
    pass

def _save_debug_screenshot(page, tag: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    page.screenshot(path=f"logs/screenshots/{tag}_{ts}.png")

def _first_visible(page, selectors: list[str], timeout: int = 8000):
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except PlaywrightTimeoutError:
            continue
    raise PlaywrightTimeoutError(f"None of the selectors became visible: {selectors}")

def _get_browser_context(p, li_at_cookie: str, proxy_url: str | None = None):
    launch_args = {"headless": True}
    if proxy_url:
        launch_args["proxy"] = {"server": proxy_url}

    browser = p.chromium.launch(**launch_args)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800}
    )
    context.add_cookies([{
        "name": "li_at",
        "value": li_at_cookie,
        "domain": ".www.linkedin.com",
        "path": "/",
        "httpOnly": True,
        "secure": True
    }])
    return browser, context

def send_message_playwright(li_at_cookie: str, profile_url: str, message_text: str, proxy_url: str | None = None) -> bool:
    with sync_playwright() as p:
        browser, context = _get_browser_context(p, li_at_cookie, proxy_url)
        page = context.new_page()
        try:
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(3.0, 6.0))

            if "login" in page.url or "checkpoint" in page.url:
                _save_debug_screenshot(page, "checkpoint_send")
                raise LinkedInCheckpointError("Session expired or checkpoint triggered.")

            msg_btn = _first_visible(page, [
                "button:has-text('Message')",
                "a[href*='/messaging/compose']"
            ])
            msg_btn.click()
            time.sleep(random.uniform(1.5, 3.0))

            input_box = _first_visible(page, [
                "div.msg-form__contenteditable[role='textbox']",
                "div[role='textbox'][aria-label*='Write a message']"
            ])
            input_box.click()
            input_box.type(message_text, delay=random.randint(35, 85))
            time.sleep(random.uniform(1.0, 2.5))

            send_btn = _first_visible(page, [
                "button.msg-form__send-button[type='submit']",
                "button[type='submit']:has-text('Send')"
            ])
            send_btn.click()
            time.sleep(random.uniform(2.0, 4.0))
            return True

        except PlaywrightTimeoutError as e:
            _save_debug_screenshot(page, "timeout_send")
            raise RuntimeError(f"UI element timeout (screenshot saved): {e}")
        finally:
            browser.close()

def fetch_unread_replies_playwright(li_at_cookie: str, proxy_url: str | None = None) -> list[dict]:
    unread_messages = []
    with sync_playwright() as p:
        browser, context = _get_browser_context(p, li_at_cookie, proxy_url)
        page = context.new_page()
        try:
            page.goto("https://www.linkedin.com/messaging/?filter=unread", wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(4.0, 7.0))

            if "login" in page.url or "checkpoint" in page.url:
                _save_debug_screenshot(page, "checkpoint_poll")
                raise LinkedInCheckpointError("Session expired or checkpoint triggered.")

            threads = page.locator("li.msg-conversation-listitem")
            for i in range(min(threads.count(), 10)):
                threads.nth(i).click()
                time.sleep(random.uniform(2.0, 3.5))

                profile_link_el = page.locator("a.msg-thread__link-to-profile").first
                if profile_link_el.count() == 0:
                    continue
                sender_slug = (profile_link_el.get_attribute("href") or "").strip("/").split("/")[-1]

                msg_bubbles = page.locator("p.msg-s-event-listitem__body")
                if msg_bubbles.count() > 0:
                    unread_messages.append({
                        "sender_id": sender_slug,
                        "text": msg_bubbles.last.inner_text().strip()
                    })
            return unread_messages
        finally:
            browser.close()