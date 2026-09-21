import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken


def _fernet(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(value: str, secret: str) -> str:
    return _fernet(secret).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str, secret: str) -> str:
    try:
        return _fernet(secret).decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt stored data. APP_SECRET may have changed.") from exc
