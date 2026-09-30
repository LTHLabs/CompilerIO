from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from .config import HUB_MODE, Settings


@dataclass
class Pairing:
    code: str
    expires_at: float
    used: bool = False


class SessionManager:
    """In-memory pairing and session tokens.

    Every successful pairing creates a new, unique session_id with its own token.
    Personal mode: a single one-time code, valid for pairing_ttl_seconds after startup.
    Hub mode: exactly one valid one-time code at a time; it is replaced immediately
    after a successful pairing and when it expires.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.hub = settings.mode == HUB_MODE
        # Guards pairing-code consumption and replacement (pair() runs in the threadpool).
        self._lock = threading.Lock()
        self.pairing = self._new_pairing()
        self.sessions: dict[str, str] = {}  # token -> session_id

    def _new_pairing(self) -> Pairing:
        return Pairing(secrets.token_urlsafe(6), time.time() + self.settings.pairing_ttl_seconds)

    def _announce(self, reason: str) -> None:
        print(
            f"Local Agent pairing code ({reason}, valid {self.settings.pairing_ttl_seconds}s): {self.pairing.code}",
            flush=True,
        )

    def pairing_code(self) -> str:
        return self.pairing.code

    def rotate_if_expired(self) -> bool:
        """Hub only: replace an expired, unused code with a fresh one. Returns True if replaced."""
        if not self.hub:
            return False
        with self._lock:
            if self.pairing.used or time.time() <= self.pairing.expires_at:
                return False
            self.pairing = self._new_pairing()
            self._announce("previous code expired")
            return True

    def validate_origin(self, request: Request) -> None:
        origin = request.headers.get("origin")
        if origin is None or origin.rstrip("/") not in self.settings.allowed_origins:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin is not allowed.")

    def pair(self, code: str) -> str:
        with self._lock:
            pairing = self.pairing
            if (
                pairing.used
                or time.time() > pairing.expires_at
                or not secrets.compare_digest(code.encode(), pairing.code.encode())
            ):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Pairing code is invalid or expired.")
            pairing.used = True
            token = secrets.token_urlsafe(32)
            self.sessions[token] = secrets.token_urlsafe(16)
            if self.hub:
                # The consumed code is replaced atomically with the next client's code.
                self.pairing = self._new_pairing()
                self._announce("next client")
            return token

    def require_token(self, request: Request) -> str:
        """Return the session_id bound to the request's token."""
        token = request.headers.get("x-local-agent-token")
        session_id = self.sessions.get(token) if token is not None else None
        if session_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Local session token is required.")
        return session_id
