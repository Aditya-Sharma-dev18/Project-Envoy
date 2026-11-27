import random
import time
import asyncio
from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger
from jinja2 import Template
from fastapi import HTTPException

from app.config import settings
from app.sync_db import get_sync_db
from app.utils.crypto import decrypt_cookie
from app.utils.alerts import send_alert
from app.utils.rate_limiter import can_send_message, record_message_sent
from app.utils.linkedin_client import (
    send_message_playwright,
    fetch_unread_replies_playwright,
    LinkedInCheckpointError,
)
from app.utils.security import scan_inbound_text
from app.utils.llm_parser import parse_alumni_reply

celery_app = Celery("envoy_worker", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
logger = get_task_logger(__name__)

# ---------------------------------------------------------
# Celery Beat Schedule (IST)
# ---------------------------------------------------------
celery_app.conf.beat_schedule = {
    "nightly-stale-alumni-fetch": {
        "task": "app.tasks.schedule_stale_alumni_outreach",
        "schedule": crontab(hour=2, minute=0),
    },
    "hourly-inbox-poll": {
        "task": "app.tasks.poll_linkedin_inboxes",
        "schedule": crontab(minute=0),
    },
}
celery_app.conf.timezone = "Asia/Kolkata"

TEMPLATES = [
    Template("Hi {{ first_name }}, hope you're doing great! We're updating our official alumni directory for the {{ batch }} batch. Are you still with {{ last_company }}, or have you transitioned to a new role recently? Just a quick one-line reply helps us keep records accurate!"),
    Template("Hey {{ first_name }}! Checking in from the college alumni cell. We're running a quick periodic check on our records. Could you confirm your current company and designation whenever you get a moment? Thanks a ton!"),
    Template("Hello {{ first_name }}, greetings from your alma mater! We are compiling current placement records for the {{ batch }} batch. Could you share your latest work update (current organization and city)? Best wishes!"),
]

# ---------------------------------------------------------
# Helpers: Account Pool & Cooldown
# ---------------------------------------------------------
def _get_next_available_account():
    with get_sync_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, account_name, li_at_cookie, proxy_url FROM linkedin_accounts "
                "WHERE status = 'ACTIVE' ORDER BY last_used_at ASC"
            )
            for acc_id, name, enc_cookie, proxy_url in cur.fetchall():
                if can_send_message(str(acc_id)):
                    cur.execute(
                        "UPDATE linkedin_accounts SET last_used_at = NOW() WHERE id = %s",
                        (acc_id,),
                    )
                    return {
                        "id": acc_id,
                        "account_name": name,
                        "li_at_cookie": decrypt_cookie(enc_cookie),
                        "proxy_url": proxy_url,
                    }
    return None

def _mark_account_cooldown(account_id: int, account_name: str, reason: str):
    with get_sync_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE linkedin_accounts SET status = 'COOLDOWN' WHERE id = %s",
                (account_id,),
            )
    send_alert(f"Account [{account_name}] moved to COOLDOWN. Reason: {reason}")

# ---------------------------------------------------------
# 1. Producer Task: Queue 150 Stale Alumni (10 accounts x 15)
# ---------------------------------------------------------
@celery_app.task(name="app.tasks.schedule_stale_alumni_outreach")
def schedule_stale_alumni_outreach():
    with get_sync_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, first_name, graduation_year, current_company, linkedin_url
                FROM alumni
                WHERE verification_status = 'STALE'
                  AND last_verified_at < NOW() - INTERVAL '180 days'
                  AND linkedin_url IS NOT NULL
                ORDER BY last_verified_at ASC
                LIMIT 150
                FOR UPDATE SKIP LOCKED;
                """
            )
            rows = cur.fetchall()
            for row_id, fname, grad_year, company, li_url in rows:
                dispatch_linkedin_message.delay(
                    alumni_id=str(row_id),
                    first_name=fname,
                    batch=str(grad_year),
                    last_company=company,
                    profile_url=li_url,
                )
                cur.execute(
                    "UPDATE alumni SET verification_status = 'OUTREACH_QUEUED' WHERE id = %s",
                    (row_id,),
                )
    logger.info(f"Queued {len(rows)} stale alumni for outreach.")

# ---------------------------------------------------------
# 2. Consumer Task: Round-Robin Playwright Dispatch
# ---------------------------------------------------------
@celery_app.task(bind=True, max_retries=3, name="app.tasks.dispatch_linkedin_message")
def dispatch_linkedin_message(
    self, alumni_id: str, first_name: str, batch: str, last_company: str, profile_url: str
):
    account = _get_next_available_account()
    if not account:
        logger.warning("All active LinkedIn accounts hit daily limit. Skipping.")
        return {"status": "all_accounts_rate_limited"}

    message_body = random.choice(TEMPLATES).render(
        first_name=first_name,
        batch=batch,
        last_company=last_company or "your previous organization",
    )

    try:
        logger.info(f"Messaging {first_name} via [{account['account_name']}]")
        send_message_playwright(
            li_at_cookie=account["li_at_cookie"],
            profile_url=profile_url,
            message_text=message_body,
            proxy_url=account["proxy_url"],
        )
        record_message_sent(str(account["id"]))

        delay = random.randint(120, 240)
        logger.info(f"Sent. Sleeping {delay}s for anti-ban jitter.")
        time.sleep(delay)
        return {"status": "success", "account_used": account["account_name"]}

    except LinkedInCheckpointError:
        _mark_account_cooldown(account["id"], account["account_name"], "Checkpoint during outbound DM")
        raise self.retry(countdown=60)

    except Exception as e:
        logger.error(f"Failed to message {alumni_id}: {e}")
        return {"status": "failed", "error": str(e)}

# ---------------------------------------------------------
# 3. Inbound Poller: Scrape Unread Replies -> LLM -> DB
# ---------------------------------------------------------
@celery_app.task(name="app.tasks.poll_linkedin_inboxes")
def poll_linkedin_inboxes():
    with get_sync_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, account_name, li_at_cookie, proxy_url "
                "FROM linkedin_accounts WHERE status = 'ACTIVE'"
            )
            accounts = cur.fetchall()

    for acc_id, acc_name, enc_cookie, proxy_url in accounts:
        try:
            raw_cookie = decrypt_cookie(enc_cookie)
            replies = fetch_unread_replies_playwright(raw_cookie, proxy_url=proxy_url)

            for reply in replies:
                try:
                    scan_inbound_text(reply["text"])
                    extracted = asyncio.run(parse_alumni_reply(reply["text"]))

                    with get_sync_db() as conn:
                        with conn.cursor() as cur:
                            if extracted.confidence_score >= 0.85:
                                cur.execute(
                                    """
                                    UPDATE alumni
                                    SET current_company = COALESCE(%s, current_company),
                                        current_designation = COALESCE(%s, current_designation),
                                        current_location = COALESCE(%s, current_location),
                                        last_verified_at = NOW(),
                                        verification_status = 'COMPLETED',
                                        raw_reply_text = %s
                                    WHERE linkedin_url LIKE '%%' || %s || '%%'
                                    """,
                                    (
                                        extracted.current_company,
                                        extracted.current_designation,
                                        extracted.current_location,
                                        reply["text"],
                                        reply["sender_id"],
                                    ),
                                )
                            else:
                                cur.execute(
                                    """
                                    UPDATE alumni
                                    SET verification_status = 'NEEDS_HUMAN_REVIEW',
                                        raw_reply_text = %s
                                    WHERE linkedin_url LIKE '%%' || %s || '%%'
                                    """,
                                    (reply["text"], reply["sender_id"]),
                                )
                except HTTPException:
                    logger.warning(f"Blocked prompt injection from {reply['sender_id']}")
                except Exception as e:
                    logger.error(f"Error parsing reply from {reply['sender_id']}: {e}")

            time.sleep(random.randint(15, 30))

        except LinkedInCheckpointError:
            _mark_account_cooldown(acc_id, acc_name, "Checkpoint during inbox poll")
        except Exception as e:
            logger.error(f"Inbox poll failed for [{acc_name}]: {e}")