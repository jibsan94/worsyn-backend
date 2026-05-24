"""Symmetric encryption for sensitive settings (SMTP password, SSO bind password, etc.).

Uses Fernet (AES-128-CBC + HMAC-SHA256) from `cryptography`. The key comes from
the `WORSYN_SETTINGS_KEY` env var. In dev, if the env var is missing, a stable
key derived from a hardcoded dev passphrase is used and a warning is logged —
**never deploy without setting the env var**.

To generate a fresh key (one-off, do this once per environment):

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Then set:  WORSYN_SETTINGS_KEY=<the-base64-key>

Rotation: any field encrypted with the old key becomes unreadable after rotation.
Plan: keep a list of acceptable keys; encrypt with [0], try decrypt with each.
v1 keeps it simple: single key.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)

_DEV_PASSPHRASE = "worsyn-dev-do-not-use-in-prod"


def _resolve_key() -> bytes:
    val = os.getenv("WORSYN_SETTINGS_KEY")
    if val:
        # Accept either a urlsafe-b64 Fernet key or any string we hash into one
        try:
            Fernet(val.encode())  # validate
            return val.encode()
        except Exception:
            digest = hashlib.sha256(val.encode()).digest()
            return base64.urlsafe_b64encode(digest)
    # Dev fallback
    log.warning("WORSYN_SETTINGS_KEY no configurada — usando clave de desarrollo. NO usar en producción.")
    return base64.urlsafe_b64encode(hashlib.sha256(_DEV_PASSPHRASE.encode()).digest())


_fernet: Fernet | None = None


def fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_resolve_key())
    return _fernet


def encrypt(plain: str) -> str:
    """Encrypt a plain string. Returns urlsafe-base64 ciphertext (str). Empty
    or None plaintext → empty string (we store NULL/"" verbatim)."""
    if not plain:
        return ""
    return fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt. Returns "" for empty/None input. Raises ValueError if the token
    is invalid (wrong key, corrupted, never-encrypted)."""
    if not token:
        return ""
    try:
        return fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("No se puede descifrar el valor (clave incorrecta o dato corrupto)") from e
