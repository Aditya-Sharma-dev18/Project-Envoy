from cryptography.fernet import Fernet
from app.config import settings

_cipher = Fernet(settings.COOKIE_ENCRYPTION_KEY.encode())

def encrypt_cookie(raw_cookie: str) -> str:
    return _cipher.encrypt(raw_cookie.encode()).decode()

def decrypt_cookie(encrypted_cookie: str) -> str:
    return _cipher.decrypt(encrypted_cookie.encode()).decode()