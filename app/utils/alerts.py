import httpx
from loguru import logger
from app.config import settings

def send_alert(message: str):
    logger.warning(f"ALERT: {message}")
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        httpx.post(url, json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": f"🚨 Project Envoy:\n{message}"}, timeout=10.0)
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")