import secrets
from fastapi import FastAPI, Header, HTTPException, Depends, status
from app.config import settings
from app.sync_db import get_sync_db
from app.tasks import schedule_stale_alumni_outreach, poll_linkedin_inboxes

app = FastAPI(title="Project Envoy - Control API")


def verify_admin(x_admin_password: str = Header(...)):
    """Dependency that validates the admin password using constant-time comparison."""
    if not secrets.compare_digest(x_admin_password, settings.ADMIN_PASSWORD):
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
    except Exception:
        raise HTTPException(status_code=503, detail="Database health check failed")


@app.get("/stats", dependencies=[Depends(verify_admin)])
def get_pipeline_stats():
    """Returns live counts of alumni statuses and LinkedIn account pool health."""
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


@app.post(
    "/admin/trigger-outreach",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_admin)],
)
def trigger_outreach_now():
    """Manually triggers the nightly stale-alumni batch (useful for testing)."""
    task = schedule_stale_alumni_outreach.delay()
    return {"status": "queued", "task_id": task.id}


@app.post(
    "/admin/trigger-poll",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_admin)],
)
def trigger_inbox_poll_now():
    """Manually triggers the hourly LinkedIn inbox scraper."""
    task = poll_linkedin_inboxes.delay()
    return {"status": "queued", "task_id": task.id}
