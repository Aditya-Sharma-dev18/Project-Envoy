import random
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

class LinkedInCheckpointError(Exception):
    """Raised when LinkedIn triggers a login wall, CAPTCHA, or account restriction."""
    pass

def _get_browser_context(p, li_at_cookie: str):
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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

def send_message_playwright(li_at_cookie: str, profile_url: str, message_text: str) -> bool:
    """Navigates to an alumni profile and sends a DM using human-like delays."""
    with sync_playwright() as p:
        browser, context = _get_browser_context(p, li_at_cookie)
        page = context.new_page()
        try:
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(3.0, 6.0))

            # Detect session expiry or security checkpoint
            if "login" in page.url or "checkpoint" in page.url:
                raise LinkedInCheckpointError("Session expired or checkpoint triggered.")

            # Click the primary 'Message' button on the profile
            msg_button = page.locator("button:has-text('Message')").first
            msg_button.wait_for(state="visible", timeout=10000)
            msg_button.click()
            time.sleep(random.uniform(1.5, 3.0))

            # Locate the chat input box and type like a human
            input_box = page.locator("div.msg-form__contenteditable[role='textbox']").last
            input_box.wait_for(state="visible", timeout=10000)
            input_box.click()
            input_box.type(message_text, delay=random.randint(35, 85))
            time.sleep(random.uniform(1.0, 2.5))

            # Click Send
            send_btn = page.locator("button.msg-form__send-button[type='submit']").last
            send_btn.click()
            time.sleep(random.uniform(2.0, 4.0))
            return True

        except PlaywrightTimeoutError as e:
            raise RuntimeError(f"UI element not found (likely not a 1st-degree connection): {e}")
        finally:
            browser.close()

def fetch_unread_replies_playwright(li_at_cookie: str) -> list[dict]:
    """Scrapes unread messages from LinkedIn Messaging inbox."""
    unread_messages = []
    with sync_playwright() as p:
        browser, context = _get_browser_context(p, li_at_cookie)
        page = context.new_page()
        try:
            page.goto("https://www.linkedin.com/messaging/?filter=unread", wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(4.0, 7.0))

            if "login" in page.url or "checkpoint" in page.url:
                raise LinkedInCheckpointError("Session expired or checkpoint triggered.")

            # Grab all unread conversation threads in the left sidebar
            threads = page.locator("li.msg-conversation-listitem")
            count = threads.count()

            for i in range(min(count, 10)):  # Process max 10 unread threads per poll
                threads.nth(i).click()
                time.sleep(random.uniform(2.0, 3.5))

                # Extract sender profile link from the thread header
                profile_link_el = page.locator("a.msg-thread__link-to-profile").first
                if profile_link_el.count() == 0:
                    continue
                profile_href = profile_link_el.get_attribute("href") or ""
                sender_slug = profile_href.strip("/").split("/")[-1]

                # Extract the latest message bubble text
                msg_bubbles = page.locator("p.msg-s-event-listitem__body")
                if msg_bubbles.count() > 0:
                    latest_text = msg_bubbles.last.inner_text().strip()
                    unread_messages.append({
                        "sender_id": sender_slug,
                        "text": latest_text
                    })

            return unread_messages
        finally:
            browser.close()