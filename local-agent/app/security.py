from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from .config import Settings


@dataclass
class Pairing:
    code: str
    expires_at: float
    used: bool = False


class SessionManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pairing = Pairing(secrets.token_urlsafe(6), time.time() + settings.pairing_ttl_seconds)
        self.tokens: set[str] = set()

    def pairing_code(self) -> str:
        return self.pairing.code

    def validate_origin(self, request: Request) -> None:
        origin = request.headers.get("origin")
        if origin is None or origin.rstrip("/") not in self.settings.allowed_origins:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin is not allowed.")

    def pair(self, code: str) -> str:
        if self.pairing.used or time.time() > self.pairing.expires_at or not secrets.compare_digest(code, self.pairing.code):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Pairing code is invalid or expired.")
        self.pairing.used = True
        token = secrets.token_urlsafe(32)
        self.tokens.add(token)
        return token

    def require_token(self, request: Request) -> None:
        token = request.headers.get("x-local-agent-token")
        if token is None or token not in self.tokens:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Local session token is required.")
