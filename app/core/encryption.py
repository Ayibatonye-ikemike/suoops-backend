"""Simple Fernet-based encryption utilities for pilot column encryption.

If ENCRYPTION_KEY not set, functions fall back to passthrough (no-op) to avoid
runtime failures during gradual rollout.
"""
from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore

logger = logging.getLogger(__name__)


@lru_cache
def _get_cipher() -> Fernet | None:
    key = os.getenv("ENCRYPTION_KEY")
    if not key or Fernet is None:
        return None
    try:
        # Support raw 32-byte key or urlsafe base64 encoded
        if len(key) == 32:
            key = base64.urlsafe_b64encode(key.encode()).decode()
        return Fernet(key)
    except Exception:  # noqa: BLE001
        logger.warning("Invalid ENCRYPTION_KEY; encryption disabled")
        return None


def encrypt_value(value: str | None) -> str | None:
    if value is None:
        return None
    cipher = _get_cipher()
    if not cipher:
        return value
    try:
        return cipher.encrypt(value.encode()).decode()
    except Exception:  # noqa: BLE001
        logger.debug("Encryption failed; returning plaintext")
        return value


def decrypt_value(value: str | None) -> str | None:
    if value is None:
        return None
    cipher = _get_cipher()
    if not cipher:
        return value
    try:
        return cipher.decrypt(value.encode()).decode()
    except InvalidToken:
        logger.debug("Decryption token invalid; returning ciphertext")
        return value
    except Exception:  # noqa: BLE001
        logger.debug("Decryption failed; returning ciphertext")
        return value
