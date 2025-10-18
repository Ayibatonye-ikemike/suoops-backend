from __future__ import annotations

import secrets
import time


def generate_id(prefix: str) -> str:
    ts = int(time.time() * 1000)
    rand = secrets.token_hex(3)
    return f"{prefix}-{ts}-{rand}".upper()
