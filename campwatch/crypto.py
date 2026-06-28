import hashlib
import base64
import os

# 암호화 키: 환경변수 CAMPWATCH_SECRET 없으면 app secret key 사용
_SECRET = os.environ.get('CAMPWATCH_SECRET', 'campwatch-secret-change-me')

def _fernet():
    from cryptography.fernet import Fernet
    key = hashlib.sha256(_SECRET.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

def encrypt_text(text: str) -> str | None:
    if not text:
        return None
    return _fernet().encrypt(text.encode()).decode()

def decrypt_text(val: str) -> str | None:
    """Fernet 복호화. 복호화 실패 시 None 반환 (잘못된 키 또는 손상된 값)."""
    if not val:
        return None
    try:
        return _fernet().decrypt(val.encode()).decode()
    except Exception:
        return None
