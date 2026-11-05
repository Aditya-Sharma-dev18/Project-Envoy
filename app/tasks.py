import random
import time
import httpx
import asyncio
from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger
from jinja2 import Template

from app.config import settings
from app.database import db

# Initialize Celery app tied to the Redis broker
celery_app = Celery(
    "envoy_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

logger = get_task_logger(__name__)

# ---------------------------------------------------------
# Celery Beat Schedule (Runs every night at 2:00 AM)
# ---------------------------------------------------------
celery_app.conf.beat_schedule = {
    'nightly-stale-alumni-fetch': {
        'task': 'app.tasks.schedule_stale_alumni_outreach',
        'schedule': crontab(hour=2, minute=0), # 2:00 AM server time
    },
}
celery_app.conf.timezone = 'UTC'

# ---------------------------------------------------------
# 1. Producer Task: The Nightly Database Query
# ---------------------------------------------------------
@celery_app.task(name='app.tasks.schedule_stale_alumni_outreach')
def schedule_stale_alumni_outreach():
    """
    Synchronous Celery wrapper that runs the async database query.
    """
    asyncio.run(_async_fetch_and_queue())

async def _async_fetch_and_queue():
    """
    Fetches the 20 oldest stale records and queues them for messaging.
    Updates their status to prevent duplicate messages the next night.
    """
    await db.connect()
    
    try:
        async with db.pool.acquire() as conn:
            # Fetch exactly 20 records to respect the single-account daily limit
            stale_alumni = await conn.fetch(
                """
                SELECT id, first_name, graduation_year, current_company, linkedin_url
                FROM alumni
                WHERE verification_status = 'STALE'
                  AND last_verified_at < NOW() - INTERVAL '180 days'
                  AND linkedin_url IS NOT NULL
                ORDER BY last_verified_at ASC
                LIMIT 20
                FOR UPDATE SKIP LOCKED; -- Prevents race conditions if multiple workers run
                """
            )
            
            if not stale_alumni:
                logger.info("No stale alumni found for outreach.")
                return

            for row in stale_alumni:
                # Extract the raw LinkedIn ID from the URL string
                # (Assumes linkedin_url format is standard, otherwise rely on a stored linkedin_id column)
                linkedin_user_id = row['linkedin_url'].strip('/').split('/')[-1]

                # Queue the outbound message task
                dispatch_linkedin_message.delay(
                    alumni_id=str(row['id']),
                    first_name=row['first_name'],
                    batch=str(row['graduation_year']),
                    last_company=row['