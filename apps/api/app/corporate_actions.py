"""Authorized corporate-action ingestion without speculative price adjustment."""

import csv
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO

from sqlalchemy import select

from app.database import CorporateActionRecord, SecurityRecord, SessionLocal
from app.schemas import CorporateAction, CorporateActionImportResult

ACTION_TYPES = {"stock_split", "cash_dividend", "bonus_share", "rights_issue", "other"}
VERIFICATION_STATUSES = {"verified", "unverified", "rejected"}


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip())
    if parsed.tzinfo is None:
        raise ValueError("effective_at must include a timezone")
    return parsed.astimezone(UTC)


def _decimal(value: str | None) -> Decimal | None:
    return Decimal(value.strip()) if value and value.strip() else None


def import_corporate_actions(
    symbol: str, content: str, default_source: str
) -> CorporateActionImportResult:
    inserted = updated = rejected = 0
    errors = []
    with SessionLocal() as session:
        security = session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == symbol.strip().upper())
        )
        if security is None:
            raise ValueError(f"Mã {symbol.strip().upper()} chưa có trong securities master.")
        seen = set()
        for line_number, row in enumerate(csv.DictReader(StringIO(content)), start=2):
            try:
                action_type = (row.get("action_type") or "").strip().lower()
                if action_type not in ACTION_TYPES:
                    raise ValueError(f"action_type must be one of {sorted(ACTION_TYPES)}")
                effective_at = _timestamp(row.get("effective_at") or "")
                source_name = (row.get("source_name") or default_source).strip()[:128]
                if not source_name:
                    raise ValueError("source_name is required")
                key = (action_type, effective_at, source_name)
                if key in seen:
                    raise ValueError("duplicate corporate action in import")
                seen.add(key)
                ratio = _decimal(row.get("ratio"))
                cash_amount = _decimal(row.get("cash_amount"))
                if ratio is not None and ratio <= 0:
                    raise ValueError("ratio must be positive")
                if cash_amount is not None and cash_amount < 0:
                    raise ValueError("cash_amount must not be negative")
                if action_type in {"stock_split", "bonus_share", "rights_issue"} and ratio is None:
                    raise ValueError(f"ratio is required for {action_type}")
                if action_type == "cash_dividend" and cash_amount is None:
                    raise ValueError("cash_amount is required for cash_dividend")
                verification = (row.get("verification_status") or "unverified").strip().lower()
                if verification not in VERIFICATION_STATUSES:
                    raise ValueError(
                        f"verification_status must be one of {sorted(VERIFICATION_STATUSES)}"
                    )
                existing = session.scalar(
                    select(CorporateActionRecord).where(
                        CorporateActionRecord.security_id == security.id,
                        CorporateActionRecord.action_type == action_type,
                        CorporateActionRecord.effective_at == effective_at,
                        CorporateActionRecord.source_name == source_name,
                    )
                )
                values = {
                    "ratio": ratio,
                    "cash_amount": cash_amount,
                    "source_url": (row.get("source_url") or "").strip() or None,
                    "verification_status": verification,
                    "retrieved_at": datetime.now(UTC),
                }
                if existing is None:
                    session.add(
                        CorporateActionRecord(
                            security_id=security.id,
                            action_type=action_type,
                            effective_at=effective_at,
                            source_name=source_name,
                            **values,
                        )
                    )
                    inserted += 1
                else:
                    for field, value in values.items():
                        setattr(existing, field, value)
                    updated += 1
            except (InvalidOperation, TypeError, ValueError) as exc:
                rejected += 1
                errors.append(f"line {line_number}: {exc}")
        session.commit()
    return CorporateActionImportResult(
        inserted=inserted, updated=updated, rejected=rejected, errors=errors[:100]
    )


def list_corporate_actions(symbol: str) -> list[CorporateAction]:
    with SessionLocal() as session:
        security = session.scalar(
            select(SecurityRecord).where(SecurityRecord.symbol == symbol.strip().upper())
        )
        if security is None:
            raise LookupError(f"Mã {symbol.strip().upper()} chưa có trong securities master.")
        rows = session.scalars(
            select(CorporateActionRecord)
            .where(CorporateActionRecord.security_id == security.id)
            .order_by(CorporateActionRecord.effective_at.desc())
        ).all()
        return [
            CorporateAction(
                action_type=row.action_type,
                effective_at=row.effective_at,
                ratio=float(row.ratio) if row.ratio is not None else None,
                cash_amount=float(row.cash_amount) if row.cash_amount is not None else None,
                source_name=row.source_name,
                source_url=row.source_url,
                verification_status=row.verification_status,
                retrieved_at=row.retrieved_at,
            )
            for row in rows
        ]
