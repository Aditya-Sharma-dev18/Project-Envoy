from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, status
import asyncpg

from app.database import db
from app.schemas import UnipileWebhookPayload
from app.utils.security import scan_inbound_text
from app.utils.llm_parser import parse_alumni_reply

# ---------------------------------------------------------
# Lifespan Event: Manages DB pool startup and shutdown
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the async database pool when the server boots
    await db.connect()
    yield
    # Safely close database connections when the server shuts down
    await db.disconnect()

app = FastAPI(title="Project Envoy - Webhook Listener", lifespan=lifespan)


# ---------------------------------------------------------
# Background Worker: Handles AI extraction and DB writes
# ---------------------------------------------------------
async def process_inbound_message(payload: UnipileWebhookPayload):
    """
    Runs in the background. Calls the LLM to parse the text, 
    then updates the PostgreSQL database safely based on confidence.
    """
    try:
        # 1. Parse the messy text into clean JSON using the LLM
        extracted_data = await parse_alumni_reply(payload.text)
        
        # 2. Acquire a database connection from the pool
        async with db.pool.acquire() as conn:
            # 3. Production Gating: High confidence = Auto-commit
            if extracted_data.confidence_score >= 0.85:
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
                    extracted_data.current_company,
                    extracted_data.current_designation,
                    extracted_data.current_location,
                    payload.text,
                    payload.sender_id  # Matching LinkedIn ID to our DB record
                )
            
            # Low confidence = Flag for human review
            else:
                await conn.execute(
                    """
                    UPDATE alumni
                    SET verification_status = 'NEEDS_HUMAN_REVIEW',
                        raw_reply_text = $1
                    WHERE linkedin_url LIKE '%' || $2 || '%'
                    """,
                    payload.text,
                    payload.sender_id
                )
    except Exception as e:
        # In production, replace this with a proper logger (e.g., Loguru)
        print(f"Error processing webhook for sender {payload.sender_id}: {e}")


# ---------------------------------------------------------
# Webhook Endpoint: Receives data from Unipile
# ---------------------------------------------------------
@app.post("/webhooks/unipile", status_code=status.HTTP_202_ACCEPTED)
async def handle_unipile_webhook(
    payload: UnipileWebhookPayload, 
    background_tasks: BackgroundTasks
):
    """
    Receives incoming LinkedIn replies. Fast-fails malicious prompts 
    and offloads processing to the background.
    """
    # 1. Security Check (