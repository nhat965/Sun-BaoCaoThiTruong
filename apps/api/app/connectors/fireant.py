from datetime import UTC, datetime
from time import perf_counter
from typing import ClassVar

import httpx

from app.schemas import SourceStatus


class FireAntConnector:
    """Authorized FireAnt boundary; data methods stay disabled until scopes are configured."""

    name = "FireAnt"
    documented_scopes: ClassVar[set[str]] = {
        "companies-read",
        "finance-read",
        "posts-read",
        "accounts-read",
    }

    def __init__(self, base_url: str, access_token: str | None, timeout: float = 12) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout

    async def status(self) -> SourceStatus:
        if not self.access_token:
            return SourceStatus(
                name=self.name,
                capabilities=sorted(self.documented_scopes),
                authentication="OAuth2 bearer token with explicit scopes",
                availability="unavailable",
                freshness="depends on licensed capability",
                licensing="Requires FireAnt authorization and applicable data agreement.",
                last_checked_at=datetime.now(UTC),
                message="BLOCKED: FIREANT_ACCESS_TOKEN is not configured; no data endpoint was called.",
            )
        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/monitoring/status",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                )
            available = response.status_code == 200
            message = (
                f"HTTP {response.status_code}; connectivity only, capability scopes not yet proven."
            )
        except httpx.HTTPError as exc:
            available = False
            message = f"Health request failed: {exc}"
        return SourceStatus(
            name=self.name,
            capabilities=sorted(self.documented_scopes),
            authentication="OAuth2 bearer token with explicit scopes",
            availability="available" if available else "unavailable",
            freshness="depends on licensed capability",
            licensing="Requires FireAnt authorization and applicable data agreement.",
            last_checked_at=datetime.now(UTC),
            message=f"{message} latency={int((perf_counter() - started) * 1000)}ms",
        )

    async def prices(self, *args, **kwargs):
        raise RuntimeError("FireAnt price scope is not verified; no data request was made.")

    async def financials(self, *args, **kwargs):
        raise RuntimeError("FireAnt finance-read scope is not verified; no data request was made.")

    async def news(self, *args, **kwargs):
        raise RuntimeError("FireAnt posts-read scope is not verified; no data request was made.")
