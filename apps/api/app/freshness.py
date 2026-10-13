"""Conservative freshness and market-session evidence helpers.

Freshness is not a wall-clock SLA.  A market observation can be delayed,
historical, synthetic, or tied to a session that cannot be confirmed without
an official exchange calendar.  These helpers deliberately return
``unconfirmed``/``unknown`` instead of presenting such rows as realtime.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

FRESHNESS_STATUSES = {
    "fresh",
    "stale",
    "delayed",
    "historical",
    "fixture",
    "unconfirmed",
    "unknown",
}


@dataclass(frozen=True)
class FreshnessAssessment:
    status: str
    basis: str
    session_status: str
    calendar_source: str


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _candidate_previous_session(session_date: date) -> date:
    candidate = session_date - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def assess_freshness(
    *,
    market_timestamp: datetime | None,
    market_session_date: date | None = None,
    source_mode: str | None = None,
    provider_freshness: str | None = None,
    now: datetime | None = None,
    timezone_name: str = "Asia/Ho_Chi_Minh",
    official_sessions: Iterable[date] | None = None,
) -> FreshnessAssessment:
    """Assess freshness with explicit provenance and session evidence.

    An official session list, when supplied, is authoritative.  Without one,
    weekdays are only candidates: a recent row is labelled ``unconfirmed``
    unless the provider explicitly says delayed/historical/fixture.  A two-day
    wall-clock fallback is used only to identify clearly old rows, never as
    proof that a row is current.
    """

    if market_timestamp is None:
        return FreshnessAssessment("unknown", "missing_market_timestamp", "unknown", "none")

    mode = (source_mode or "unknown").strip().lower()
    declared = (provider_freshness or "").strip().lower()
    if mode == "fixture" or declared == "fixture":
        return FreshnessAssessment("fixture", "synthetic_fixture", "not_a_market_session", "fixture")
    if mode == "historical" or "historical" in declared:
        return FreshnessAssessment("historical", "historical_provider_metadata", "historical", "provider")

    timestamp_utc = utc(market_timestamp)
    reference = utc(now or datetime.now(UTC))
    market_tz = ZoneInfo(timezone_name)
    local_today = reference.astimezone(market_tz).date()
    session_date = market_session_date or timestamp_utc.astimezone(market_tz).date()

    if session_date > local_today:
        return FreshnessAssessment("unknown", "future_session", "invalid", "none")
    if session_date.weekday() >= 5:
        return FreshnessAssessment("unconfirmed", "weekend_session", "non_trading_candidate", "weekend_rule")

    official = sorted(set(official_sessions or []))
    if official:
        eligible = [item for item in official if item <= local_today]
        if session_date not in official:
            return FreshnessAssessment("unconfirmed", "session_not_in_official_calendar", "unlisted", "official")
        if not eligible:
            return FreshnessAssessment("unknown", "no_completed_official_session", "unknown", "official")
        latest = eligible[-1]
        session_status = "latest_official" if session_date == latest else "prior_official"
        if session_date != latest:
            return FreshnessAssessment("stale", "behind_latest_official_session", session_status, "official")
        if "delayed" in declared or mode == "delayed":
            return FreshnessAssessment("delayed", "provider_declared_delayed", session_status, "official")
        return FreshnessAssessment("fresh", "latest_official_session", session_status, "official")

    # No licensed calendar is connected.  Use business-day distance only as a
    # conservative staleness signal; it cannot prove a current trading day.
    candidate_previous = _candidate_previous_session(local_today)
    if session_date in {local_today, candidate_previous}:
        session_status = "weekday_candidate"
        if "delayed" in declared or mode == "delayed":
            return FreshnessAssessment("delayed", "provider_declared_delayed", session_status, "weekday_rule")
        return FreshnessAssessment("unconfirmed", "no_official_session_calendar", session_status, "weekday_rule")

    business_age = sum(
        (session_date + timedelta(days=offset)).weekday() < 5
        for offset in range((local_today - session_date).days + 1)
    )
    if business_age > 2 or reference - timestamp_utc > timedelta(days=2):
        basis = "old_session_without_official_calendar"
        if "delayed" in declared or mode == "delayed":
            basis = "old_delayed_session_without_official_calendar"
        return FreshnessAssessment("stale", basis, "older_weekday_candidate", "weekday_rule")
    if "delayed" in declared or mode == "delayed":
        return FreshnessAssessment("delayed", "provider_declared_delayed", "weekday_candidate", "weekday_rule")
    return FreshnessAssessment("unconfirmed", "no_official_session_calendar", "weekday_candidate", "weekday_rule")


def assess_rows(
    rows: Iterable[object],
    *,
    now: datetime | None = None,
    timezone_name: str = "Asia/Ho_Chi_Minh",
    official_sessions: Iterable[date] | None = None,
) -> FreshnessAssessment:
    values = list(rows)
    if not values:
        return FreshnessAssessment("unknown", "no_rows", "unknown", "none")
    timestamped = [row for row in values if getattr(row, "market_timestamp", None) is not None]
    if not timestamped:
        return FreshnessAssessment("unknown", "missing_market_timestamp", "unknown", "none")
    latest = max(timestamped, key=lambda row: utc(row.market_timestamp))
    return assess_freshness(
        market_timestamp=latest.market_timestamp,
        market_session_date=getattr(latest, "market_session_date", None),
        source_mode=getattr(latest, "source_mode", None),
        provider_freshness=getattr(latest, "freshness", None),
        now=now,
        timezone_name=timezone_name,
        official_sessions=official_sessions,
    )
