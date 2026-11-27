import redis
from app.config import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

DAILY_LIMIT = 20
TTL_SECONDS = 86400  # 24 hours

# Lua script: atomically INCR the counter and set TTL on first use.
# Returns the new count so the caller knows the exact state.
_RECORD_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def can_send_message(account_id: str) -> bool:
    """Check if the LinkedIn account is under its daily send limit."""
    redis_key = f"rate_limit:linkedin:{account_id}"
    current = redis_client.get(redis_key)
    return current is None or int(current) < DAILY_LIMIT


def record_message_sent(account_id: str) -> int:
    """
    Atomically records a sent message with an auto-expiring daily counter.
    Returns the new count for the day.
    """
    redis_key = f"rate_limit:linkedin:{account_id}"
    return redis_client.eval(_RECORD_SCRIPT, 1, redis_key, TTL_SECONDS)


def get_remaining_capacity(account_id: str) -> int:
    """Returns how many messages the account can still send today."""
    redis_key = f"rate_limit:linkedin:{account_id}"
    current = redis_client.get(redis_key)
    return DAILY_LIMIT - int(current) if current else DAILY_LIMIT
