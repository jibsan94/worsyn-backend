import base64
import io
from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp
import qrcode
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain[:72], hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain[:72])


def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"sub": str(subject), "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str | Any) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": str(subject), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_partial_token(subject: str | Any) -> str:
    """Short-lived token (5 min) used while awaiting TOTP verification during login."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {"sub": str(subject), "exp": expire, "type": "2fa_pending"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_org_select_token(email: str, slugs: list[str]) -> str:
    """Short-lived token (10 min) issued after credential validation to allow org selection."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {"sub": email, "orgs": slugs, "exp": expire, "type": "org_select"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return {}


# ── TOTP utilities ────────────────────────────────────────────────────────────

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str, issuer: str = "Worsyn Admin") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


def generate_qr_base64(uri: str) -> str:
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
