import random
import time
import asyncio
from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger
from jinja2 import Template
from fastapi import HTTPException

from app.config import settings
from app.database import db
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
# Celery Beat Schedule
# ---------------------------------------------------------
celery_app.conf.beat_schedule = {
    "nightly-stale-alumni-fetch": {
        "task": "app.tasks.schedule_stale_alumni_outreach",
        "schedule": crontab(hour=2, minute=0),
    },
    "hourly-inbox-poll": {
        "task": "app.tasks.poll_linkedin_inboxes",
        "schedule": crontab(minute=0),  # Every hour at :00
    },
}
celery_app.conf.timezone = "Asia/Kolkata"

TEMPLATES = [
    Template("Hi {{ first_name }}, hope you're doing great! We're updating our official alumni directory for the {{ batch }} batch. Are you still with {{ last_company }}, or have you transitioned to a new role recently? Just a quick one-line reply helps us keep records accurate!"),
    Template("Hey {{ first_name }}! Checking in from the college alumni cell. We're running a quick periodic check on our records. Could you confirm your current company and designation whenever you get a moment? Thanks a ton!"),
    Template("Hello {{ first_name }}, greetings from your alma mater! We are compiling current placement records for the {{ batch }} batch. Could you share your latest work update (current organization and city)? Best wishes!"),
]

# ---------------------------------------------------------
# Helper: Async DB Operations for Account Pool
# ---------------------------------------------------------
async def _get_next_available_account():
    await db.connect()
    try:
        async with db.pool.acquire() as conn:
            accounts = await conn.fetch(
                "SELECT id, account_name, li_at_cookie FROM linkedin_accounts "
                "WHERE status = 'ACTIVE' ORDER BY last_used_at ASC"
            )
            for acc in accounts:
                if can_send_message(str(acc["id"])):
                    await conn.execute(
                        "UPDATE linkedin_accounts SET last_used_at = NOW() WHERE id = $1",
                        acc["id"]
                    )
                    return dict(acc)
            return None
    finally:
        await db.disconnect()

async def _mark_account_cooldown(account_id: int):
    await db.connect()
    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE linkedin_accounts SET status = 'COOLDOWN' WHERE id = $1",
                account_id
            )
    finally:
        await db.disconnect()

# ---------------------------------------------------------
# 1. Producer Task: Fetch 150 Stale Alumni (10 accounts x 15)
# ---------------------------------------------------------
@celery_app.task(name="app.tasks.schedule_stale_alumni_outreach")
def schedule_stale_alumni_outreach():
    asyncio.run(_async_fetch_and_queue())

async def _async_fetch_and_queue():
    await db.connect()
    try:
        async with db.pool.acquire() as conn:
            stale_alumni = await conn.fetch(
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
            for row in stale_alumni:
                dispatch_linkedin_message.delay(
                    alumni_id=str(row["id"]),
                    first_name=row["first_name"],
                    batch=str(row["graduation_year"]),
                    last_company=row["current_company"],
                    profile_url=row["linkedin_url"],
                )
                await conn.execute(
                    "UPDATE alumni SET verification_status = 'OUTREACH_QUEUED' WHERE id = $1",
                    row["id"]
                )
            logger.info(f"Queued {len(stale_alumni)} alumni across 10-account pool.")
    finally:
        await db.disconnect()

# ---------------------------------------------------------
# 2. Consumer Task: Round-Robin Playwright Dispatch
# ---------------------------------------------------------
@celery_app.task(bind=True, max_retries=3, name="app.tasks.dispatch_linkedin_message")
def dispatch_linkedin_message(self, alumni_id: str, first_name: str, batch: str, last_company: str, profile_url: str):
    account = asyncio.run(_get_next_available_account())
    if not account:
        logger.warning("All 10 LinkedIn accounts have hit their daily 15-message limit. Skipping.")
        return {"status": "all_accounts_rate_limited"}

    template = random.choice(TEMPLATES)
    message_body = template.render(
        first_name=first_name,
        batch=batch,
        last_company=last_company or "your previous organization"
    )

    try:
        logger.info(f"Sending DM to {first_name} via Account [{account['account_name']}]")
        send_message_playwright(account["li_at_cookie"], profile_url, message_body)
        record_message_sent(str(account["id"]))

        # Mandatory jitter delay before next browser session opens
        delay = random.randint(120, 240)
        logger.info(f"Sent successfully. Sleeping {delay}s for anti-ban jitter.")
        time.sleep(delay)
        return {"status": "success", "account_used": account["account_name"]}

    except LinkedInCheckpointError:
        logger.error(f"Checkpoint hit on Account [{account['account_name']}]. Moving to COOLDOWN and retrying.")
        asyncio.run(_mark_account_cooldown(account["id"]))
        raise self.retry(countdown=60)

    except Exception as e:
        logger.error(f"Failed to message {alumni_id}: {e}")
        return {"status": "failed", "error": str(e)}

# ---------------------------------------------------------
# 3. Inbound Poller: Scrape Unread Replies -> LLM -> DB
# ---------------------------------------------------------
@celery_app.task(name="app.tasks.poll_linkedin_inboxes")
def poll_linkedin_inboxes():
    asyncio.run(_async_poll_inboxes())

async def _async_poll_inboxes():
    await db.connect()
    try:
        async with db.pool.acquire() as conn:
            accounts = await conn.fetch(
                "SELECT id, account_name, li_at_cookie FROM linkedin_accounts WHERE status = 'ACTIVE'"
            )

        for acc in accounts:
            try:
                replies = fetch_unread_replies_playwright(acc["li_at_cookie"])
                for reply in replies:
                    try:
                        # 1. Security Guardrail
                        scan_inbound_text(reply["text"])
                        # 2. LLM Extraction
                        extracted = await parse_alumni_reply(reply["text"])
                        # 3. DB Update
                        async with db.pool.acquire() as conn:
                            if extracted.confidence_score >= 0.85:
                                await conn.execute(
                                    """
                                    UPDATE alumni
                                    SET current_company = COALESCE($1, current_company),
                                        current_designation = COALESCE($2, current_designation),
                                        current_location = COALESCE($3, current_location),
                                        last_verified_at = NOW(),
                                        verification_status = 'COMPLETED',
                                        raw_reply_text = $4
                                    WHERE linkedin_url LIKE '%' || $5 || '%'
                                    """,
                                    extracted.current_company,
                                    extracted.current_designation,
                                    extracted.current_location,
                                    reply["text"],
                                    reply["sender_id"],
                                )
                            else:
                                await conn.execute(
                                    """
                                    UPDATE alumni
                                    SET verification_status = 'NEEDS_HUMAN_REVIEW',
                                        raw_reply_text = $1
                                    WHERE linkedin_url LIKE '%' || $2 || '%'
                                    """,
                                    reply["text"],
                                    reply["sender_id"],
                                )
                    except HTTPException:
                        logger.warning(f"Blocked prompt injection from {reply['sender_id']}")
                    except Exception as e:
                        logger.error(f"Error parsing reply from {reply['sender_id']}: {e}")

                time.sleep(random.randint(15, 30))  # Pause between checking different accounts

            except LinkedInCheckpointError:
                logger.error(f"Checkpoint hit while polling [{acc['account_name']}]. Marking COOLDOWN.")
                async with db.pool.acquire() as conn:
                    await conn.execute("UPDATE linkedin_accounts SET status = 'COOLDOWN' WHERE id = $1", acc["id"])
    finally:
        await db.disconnect()