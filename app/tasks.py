import time
import random
import httpx
from celery import Celery
from jinja2 import Template
from app.config import settings

# Initialize Celery connected to our Redis broker
celery_app = Celery("envoy_worker", broker=settings.REDIS_URL)

# ---------------------------------------------------------
# Spintax: Rotate templates to avoid spam filters
# ---------------------------------------------------------
TEMPLATES = [
    "Hi {{ first_name }}, hope you're doing well! Checking in from the college alumni cell. We are refreshing our directory for the {{ batch }} batch. Could you quickly confirm if you are still with {{ last_company }} or if you've recently transitioned to a new role?",
    
    "Hey {{ first_name }}! We're running a quick periodic check on our alumni records. Are you still working at {{ last_company }}? A quick yes/no or your updated role helps us a ton. Thanks!",
    
    "Hello {{ first_name }}, greetings from your alma mater! We're compiling current placement records for the {{ batch }} batch. Could you share your latest work update? Best wishes!"
]

@celery_app.task(bind=True, max_retries=3)
def send_outreach_message(
    self, 
    alumni_id: str, 
    first_name: str, 
    batch_year: int, 
    last_company: str, 
    linkedin_id: str
):
    """
    Pulls a template, sends the LinkedIn DM via Unipile, and forces 
    the worker to sleep for 3-6 minutes to protect the account.
    """
    # 1. Pick a random template and render it
    template_str = random.choice(TEMPLATES)
    compiled_template = Template(template_str)
    
    message_body = compiled_template.render(
        first_name=first_name,
        batch=batch_year,
        last_company=last_company or "your previous company"
    )
    
    # 2. Prepare the Unipile API Request
    headers = {
        "X-API-KEY": settings.UNIPILE_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "account_id": settings.LINKEDIN_ACCOUNT_ID,
        "attendees_ids": [linkedin_id],
        "text": message_body
    }
    
    # 3. Dispatch the message synchronously
    try:
        with httpx.Client() as client:
            response = client.post(
                settings.UNIPILE_DSN, 
                json=payload, 
                headers=headers, 
                timeout=10.0
            )
        response.raise_for_status()
        
    except httpx.HTTPError as exc:
        # Retry with exponential backoff if the API fails (e.g., Unipile is down)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 15)
    
    # 4. Mandatory Anti-Ban Jitter (Sleep)
    # This blocks the worker from picking up the next task in the queue immediately.
    delay_seconds = random.randint(180, 360)
    time.sleep(delay_seconds)
    
    return {
        "status": "success", 
        "alumni_id": alumni_id, 
        "slept_for": delay_seconds
    }