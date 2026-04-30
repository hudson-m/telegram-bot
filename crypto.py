import os
from cryptography.fernet import Fernet

_fernet = None

def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("ENCRYPTION_KEY não configurada")
        _fernet = Fernet(key.encode())
    return _fernet

def encrypt(text: str) -> str:
    return _get_fernet().encrypt(text.encode()).decode()

def decrypt(token: str) -> str:
    return _get_fernet().decrypt(token.encode()).decode()
