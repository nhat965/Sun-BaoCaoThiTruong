"""Header-token authentication and authorization for privileged API routes."""

import hmac
import json
import logging
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.repositories import AuditRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    role: str
    actor: str


class FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, list[float]] = {}

    def allow(self, key: str, limit: int, window_seconds: float = 60) -> bool:
        now = time.monotonic()
        events = [
            timestamp for timestamp in self._events.get(key, []) if now - timestamp < window_seconds
        ]
        if len(events) >= limit:
            self._events[key] = events
            return False
        events.append(now)
        self._events[key] = events
        return True

    def reset(self) -> None:
        self._events.clear()


admin_rate_limiter = FixedWindowRateLimiter()
llm_rate_limiter = FixedWindowRateLimiter()


def enforce_llm_rate_limit(request: Request, config: Settings) -> None:
    key = request.client.host if request.client else "unknown"
    if not llm_rate_limiter.allow(key, config.llm_rate_limit_per_minute):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Giới hạn yêu cầu AI trong một phút đã đạt.",
        )


def _audit(
    request: Request,
    *,
    actor: str,
    outcome: str,
    metadata: dict | None = None,
    action: str = "securities.import",
) -> None:
    try:
        with SessionLocal() as session:
            AuditRepository(session).record(
                actor=actor,
                action=action,
                resource="securities",
                outcome=outcome,
                source_ip=request.client.host if request.client else None,
                metadata=metadata,
            )
            session.commit()
    except Exception:  # pragma: no cover - audit must not turn auth into a data leak
        logger.exception("Unable to persist an audit event")


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def require_admin(
    request: Request,
    authorization: str | None = Header(default=None),
    config: Settings = Depends(get_settings),
) -> Principal:
    """Fail closed when admin credentials are not configured."""
    if not config.admin_api_token:
        _audit(request, actor="anonymous", outcome="blocked", metadata={"reason": "not_configured"})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is not configured.",
        )

    token = _bearer_token(authorization)
    if token is None:
        _audit(
            request,
            actor="anonymous",
            outcome="unauthorized",
            metadata={"reason": "missing_bearer"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if hmac.compare_digest(token, config.admin_api_token):
        principal = Principal(role="admin", actor="admin-token")
    elif config.reader_api_token and hmac.compare_digest(token, config.reader_api_token):
        _audit(
            request,
            actor="reader-token",
            outcome="forbidden",
            metadata={"reason": "admin_required"},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role is required.")
    else:
        _audit(
            request,
            actor="unknown-token",
            outcome="unauthorized",
            metadata={"reason": "invalid_token"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    client_key = request.client.host if request.client else "unknown"
    if not admin_rate_limiter.allow(
        f"{principal.actor}:{client_key}", config.admin_rate_limit_per_minute
    ):
        _audit(request, actor=principal.actor, outcome="rate_limited")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded."
        )
    return principal


def audit_success(
    request: Request, principal: Principal, result: object, action: str = "securities.import"
) -> None:
    _audit(
        request,
        actor=principal.actor,
        outcome="success",
        metadata=json.loads(result.model_dump_json()) if hasattr(result, "model_dump_json") else {},
        action=action,
    )


def audit_event(request: Request, *, action: str, actor: str = "anonymous", metadata: dict | None = None) -> None:
    _audit(request, actor=actor, outcome="accepted", action=action, metadata=metadata)
