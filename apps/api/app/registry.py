import csv
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from pydantic import ValidationError

from app.database import SessionLocal
from app.repositories import SecuritiesRepository
from app.schemas import SecuritiesImportResult, Security

ALLOWED_EXCHANGES = {"HOSE", "HNX", "UPCOM"}
ALLOWED_STATUSES = {"active", "inactive", "delisted", "suspended"}


def parse_security(row: dict[str, str], default_source: str) -> Security:
    symbol = row.get("symbol", "").strip().upper()
    exchange = row.get("exchange", "").strip().upper()
    status = row.get("listing_status", "active").strip().lower()
    if not symbol.isalnum() or not 1 <= len(symbol) <= 16:
        raise ValueError("symbol must be 1-16 alphanumeric characters")
    if exchange not in ALLOWED_EXCHANGES:
        raise ValueError(f"exchange must be one of {sorted(ALLOWED_EXCHANGES)}")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"listing_status must be one of {sorted(ALLOWED_STATUSES)}")
    name = row.get("name", "").strip()
    if not name:
        raise ValueError("name is required")
    provider_symbol = row.get("provider_symbol", "").strip()
    return Security(
        symbol=symbol,
        name=name,
        aliases=[item.strip() for item in row.get("aliases", "").split("|") if item.strip()],
        exchange=exchange,
        industry=row.get("industry") or None,
        sector=row.get("sector") or None,
        listing_status=status,
        security_type=row.get("security_type", "stock") or "stock",
        provider_ids={"yahoo": provider_symbol} if provider_symbol else {},
        source_name=row.get("source_name") or default_source,
        source_url=row.get("source_url") or None,
        last_updated=datetime.now(UTC),
    )


def import_securities_csv(content: str, source_name: str) -> SecuritiesImportResult:
    inserted = updated = rejected = 0
    errors: list[str] = []
    with SessionLocal() as session:
        repository = SecuritiesRepository(session)
        for line_number, row in enumerate(csv.DictReader(StringIO(content)), start=2):
            try:
                _, was_inserted = repository.upsert(parse_security(row, source_name))
                inserted += int(was_inserted)
                updated += int(not was_inserted)
            except (ValueError, ValidationError) as exc:
                rejected += 1
                errors.append(f"line {line_number}: {exc}")
        session.commit()
    return SecuritiesImportResult(
        inserted=inserted, updated=updated, rejected=rejected, errors=errors[:100]
    )


def seed_registry_if_empty() -> SecuritiesImportResult | None:
    with SessionLocal() as session:
        if SecuritiesRepository(session).search("", limit=1, include_inactive=True):
            return None
    seed_path = Path(__file__).with_name("data") / "securities_bootstrap.csv"
    return import_securities_csv(seed_path.read_text(encoding="utf-8"), "bootstrap-manual")
