from fastapi import FastAPI, Header, HTTPException, status
from app.config import settings
from app.sync_db import get_sync_db
from app.tasks import schedule_stale_alumni_outreach, poll_linkedin_inboxes

app = FastAPI(title="Project Envoy - Control API")


def _verify_admin(x_admin_password: str = Header(...)):
    if x_admin_password != settings.ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin password",
        )


@app.get("/health")
def health_check():
    """Verifies API and PostgreSQL connectivity."""
    try:
        with get_sync_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {e}")


@app.get("/stats")
def get_pipeline_stats(x_admin_password: str = Header(...)):
    """Returns live counts of alumni statuses and LinkedIn account pool health."""
    _verify_admin(x_admin_password)
    with get_sync_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT verification_status, COUNT(*) FROM alumni GROUP BY verification_status;"
            )
            alumni_stats = dict(cur.fetchall())

            cur.execute(
                "SELECT status, COUNT(*) FROM linkedin_accounts GROUP BY status;"
            )
            account_stats = dict(cur.fetchall())

    return {
        "alumni": alumni_stats,
        "linkedin_accounts": account_stats,
    }


@app.post("/admin/trigger-outreach", status_code=status.HTTP_202_ACCEPTED)
def trigger_outreach_now(x_admin_password: str = Header(...)):
    """Manually triggers the nightly stale-alumni batch (useful for testing)."""
    _verify_admin(x_admin_password)
    task = schedule_stale_alumni_outreach.delay()
    return {"status": "queued", "task_id": task.id}


@app.post("/admin/trigger-poll", status_code=status.HTTP_202_ACCEPTED)
def trigger_inbox_poll_now(x_admin_password: str = Header(...)):
    """Manually triggers the hourly LinkedIn inbox scraper."""
    _verify_admin(x_admin_password)
    task = poll_linkedin_inboxes.delay()
    return {"status": "queued", "task_id": task.id}