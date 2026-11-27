import random
import time
from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger
from jinja2 import Template

from app.config import settings
from app.sync_db import get_sync_db
from app.utils.crypto import decrypt_cookie
from app.utils.alerts import send_alert
from app.utils.rate_limiter import can_send_message, record_message_sent
from app.utils.linkedin_client import (
    send_message_playwright,
    fetch_unread_replies_playwright,
    extract_profile_slug,
    LinkedInCheckpointError,
)
from app.utils.security import scan_inbound_text, PromptInjectionError
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
    Template(
        "Hi {{ first_name }}, hope you're doing great! We're updating our official "
        "alumni directory for the {{ batch }} batch. Are you still with "
        "{{ last_company }}, or have you transitioned to a new role recently? "
        "Just a quick one-line reply helps us keep records accurate!"
    ),
    Template(
        "Hey {{ first_name }}! Checking in from the college alumni cell. We're "
        "running a quick periodic check on our records. Could you confirm your "
        "current company and designation whenever you get a moment? Thanks a ton!"
    ),
    Template(
        "Hello {{ first_name }}, greetings from your alma mater! We are compiling "
        "current placement records for the {{ batch }} batch. Could you share your "
        "latest work update (current organization and city)? Best wishes!"
    ),
]


# ---------------------------------------------------------
# Helpers: Account Pool & Cooldown
# ---------------------------------------------------------
def _get_next_available_account():
    """Round-robin selection of the least-recently-used active account under its daily limit."""
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
    """Moves an account to COOLDOWN status and sends an alert."""
    with get_sync_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE linkedin_accounts SET status = 'COOLDOWN' WHERE id = %s",
                (account_id,),
            )
    send_alert(f"Account [{account_name}] moved to COOLDOWN. Reason: {reason}")


# ---------------------------------------------------------
# 1. Producer: Queue Stale Alumni with Staggered Dispatch
# ---------------------------------------------------------
@celery_app.task(name="app.tasks.schedule_stale_alumni_outreach")
def schedule_stale_alumni_outreach():
    """Fetches stale alumni and dispatches outreach tasks with staggered scheduling.

    Instead of blocking the worker with time.sleep() between sends, each task
    is scheduled with a Celery ``countdown`` so the worker stays free for
    other work (e.g. inbox polling) in between.
    """
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
            for i, (row_id, fname, grad_year, company, li_url) in enumerate(rows):
                # Stagger ~3 min apart with up to 1 min of jitter
                dispatch_linkedin_message.apply_async(
                    kwargs={
                        "alumni_id": str(row_id),
                        "first_name": fname,
                        "batch": str(grad_year),
                        "last_company": company,
                        "profile_url": li_url,
                    },
                    countdown=i * 180 + random.randint(0, 60),
                )
                cur.execute(
                    "UPDATE alumni SET verification_status = 'OUTREACH_QUEUED' WHERE id = %s",
                    (row_id,),
                )
    logger.info(f"Queued {len(rows)} stale alumni for staggered outreach.")


# ---------------------------------------------------------
# 2. Consumer: Dispatch a Single LinkedIn Message
# ---------------------------------------------------------
@celery_app.task(bind=True, max_retries=3, name="app.tasks.dispatch_linkedin_message")
def dispatch_linkedin_message(
    self, alumni_id: str, first_name: str, batch: str, last_company: str, profile_url: str
):
    """Sends a LinkedIn message to a single alumnus and records the outreach."""
    account = _get_next_available_account()
    if not account:
        logger.warning("All active LinkedIn accounts hit daily limit. Retrying in 1 hour.")
        raise self.retry(countdown=3600)

    message_body = random.choice(TEMPLATES).render(
        first_name=first_name,
        batch=batch,
        last_company=last_company or "your previous organization",
    )

    try:
        logger.info(f"Messaging {first_name} via [{account['account_name']}]")
        result = send_message_playwright(
            li_at_cookie=account["li_at_cookie"],
            profile_url=profile_url,
            message_text=message_body,
            proxy_url=account["proxy_url"],
        )
        record_message_sent(str(account["id"]))

        # Record the outreach and update alumni status
        with get_sync_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO outreach_log
                        (alumni_id, linkedin_account_id, profile_url, message_text, status)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (alumni_id, account["id"], profile_url, message_body, result),
                )
                cur.execute(
                    "UPDATE alumni SET verification_status = 'CONTACTED' WHERE id = %s",
                    (alumni_id,),
                )

        logger.info(f"Sent ({result}) to {first_name} via [{account['account_name']}].")
        return {"status": "success", "result": result, "account_used": account["account_name"]}

    except LinkedInCheckpointError:
        _mark_account_cooldown(
            account["id"], account["account_name"], "Checkpoint during outbound DM"
        )
        raise self.retry(countdown=60)

    except Exception as e:
        logger.error(f"Failed to message {alumni_id}: {e}")
        # Reset to STALE so it can be retried in the next nightly batch
        with get_sync_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE alumni SET verification_status = 'STALE' WHERE id = %s",
                    (alumni_id,),
                )
        return {"status": "failed", "error": str(e)}


# ---------------------------------------------------------
# 3. Inbound Poller: Scrape Replies -> LLM -> DB
# ---------------------------------------------------------
@celery_app.task(name="app.tasks.poll_linkedin_inboxes")
def poll_linkedin_inboxes():
    """Polls each active LinkedIn account's inbox, parses replies with an LLM, and updates the DB."""
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
                _process_single_reply(reply)

            # Jitter between account polls to avoid detection
            time.sleep(random.randint(15, 30))

        except LinkedInCheckpointError:
            _mark_account_cooldown(acc_id, acc_name, "Checkpoint during inbox poll")
        except Exception as e:
            logger.error(f"Inbox poll failed for [{acc_name}]: {e}")


def _process_single_reply(reply: dict):
    """Processes one scraped reply: security scan -> LLM parse -> DB update."""
    profile_url = reply.get("profile_url", "unknown")
    try:
        scan_inbound_text(reply["text"])
        extracted = parse_alumni_reply(reply["text"])

        # Match the reply to an alumni record via the LinkedIn profile slug
        reply_slug = extract_profile_slug(profile_url)

        with get_sync_db() as conn:
            with conn.cursor() as cur:
                # Find the alumni who was contacted and whose LinkedIn URL contains this slug
                cur.execute(
                    """
                    SELECT id FROM alumni
                    WHERE linkedin_url LIKE %s
                      AND verification_status IN ('CONTACTED', 'OUTREACH_QUEUED')
                    LIMIT 1
                    """,
                    (f"%{reply_slug}%",),
                )
                row = cur.fetchone()
                if not row:
                    logger.warning(f"No matching contacted alumni for profile: {profile_url}")
                    return

                alumni_id = row[0]

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
                        WHERE id = %s
                        """,
                        (
                            extracted.current_company,
                            extracted.current_designation,
                            extracted.current_location,
                            reply["text"],
                            alumni_id,
                        ),
                    )
                    logger.info(
                        f"Auto-verified alumni {alumni_id} "
                        f"(confidence={extracted.confidence_score:.2f})"
                    )
                else:
                    cur.execute(
                        """
                        UPDATE alumni
                        SET verification_status = 'NEEDS_HUMAN_REVIEW',
                            raw_reply_text = %s
                        WHERE id = %s
                        """,
                        (reply["text"], alumni_id),
                    )
                    logger.info(
                        f"Flagged alumni {alumni_id} for human review "
                        f"(confidence={extracted.confidence_score:.2f})"
                    )

                # Mark reply as received in outreach log
                cur.execute(
                    """
                    UPDATE outreach_log
                    SET reply_received_at = NOW(), status = 'REPLY_RECEIVED'
                    WHERE id = (
                        SELECT id FROM outreach_log
                        WHERE alumni_id = %s AND reply_received_at IS NULL
                        ORDER BY sent_at DESC
                        LIMIT 1
                    )
                    """,
                    (str(alumni_id),),
                )

    except PromptInjectionError:
        logger.warning(f"Blocked prompt injection from reply at {profile_url}")
    except Exception as e:
        logger.error(f"Error parsing reply from {profile_url}: {e}")
