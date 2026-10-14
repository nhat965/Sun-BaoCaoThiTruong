"""Verify SSI FastConnect configuration without leaking credentials.

This script intentionally tests only the documented token endpoint. It is safe to
run in CI without credentials: that case is reported as BLOCKED, not as a fake
success. A returned token is held in memory for the duration of the request and is
never printed or persisted.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

import httpx

from app.config import Settings


def _result(status: str, message: str, **extra: object) -> int:
    payload = {
        "provider": "ssi_fastconnect",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": status,
        "message": message,
        **extra,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if status == "BLOCKED" or status == "AVAILABLE" else 1


def verify(settings: Settings, *, no_network: bool, timeout: float) -> int:
    if not settings.ssi_api_key or not settings.ssi_api_secret:
        return _result(
            "BLOCKED",
            "SSI_API_KEY and SSI_API_SECRET are not configured; no request was made.",
            environment=settings.ssi_environment,
            auth_url=settings.ssi_auth_url,
        )
    if no_network:
        return _result(
            "CONFIGURED",
            "Credentials are configured; --no-network skipped the token request.",
            environment=settings.ssi_environment,
            auth_url=settings.ssi_auth_url,
        )
    try:
        response = httpx.post(
            settings.ssi_auth_url,
            json={"apiKey": settings.ssi_api_key, "apiSecret": settings.ssi_api_secret},
            timeout=timeout,
            follow_redirects=False,
        )
        rate_headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower().startswith("x-ratelimit-")
        }
        if response.is_success:
            return _result(
                "AVAILABLE",
                "Documented SSI token request succeeded; market-data scope still requires a separate integration test.",
                environment=settings.ssi_environment,
                auth_url=settings.ssi_auth_url,
                http_status=response.status_code,
                rate_limit_headers=rate_headers,
            )
        return _result(
            "FAILED",
            "SSI token request returned a non-success status; credentials and entitlement were not accepted.",
            environment=settings.ssi_environment,
            auth_url=settings.ssi_auth_url,
            http_status=response.status_code,
            rate_limit_headers=rate_headers,
        )
    except httpx.HTTPError as exc:
        return _result(
            "FAILED",
            f"SSI token request failed: {exc.__class__.__name__}.",
            environment=settings.ssi_environment,
            auth_url=settings.ssi_auth_url,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-network", action="store_true", help="validate configuration only")
    parser.add_argument("--timeout", type=float, default=12.0)
    args = parser.parse_args()
    return verify(Settings(), no_network=args.no_network, timeout=args.timeout)


if __name__ == "__main__":
    sys.exit(main())
