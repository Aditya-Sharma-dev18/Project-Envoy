import redis
from app.config import settings

# Connect to Redis
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

DAILY_LIMIT = 20

def can_send_message(account_id: str) -> bool:
    """
    Checks if the LinkedIn account has capacity to send a message today.
    Uses Redis to track the count with an automatic 24-hour expiration.
    """
    redis_key = f"rate_limit:linkedin:{account_id}"
    
    # Check current count
    current_count = redis_client.get(redis_key)
    
    if current_count and int(current_count) >= DAILY_LIMIT:
        return False
        
    return True

def record_message_sent(account_id: str):
    """
    Increments the daily message count for the account.
    """
    redis_key = f"rate_limit:linkedin:{account_id}"
    
    # Increment count
    current_count = redis_client.incr(redis_key)
    
    # If this is the first message today, set the key to expire in 24 hours (86400 seconds)
    if current_count == 1:
        redis_client.expire(redis_key, 86400)