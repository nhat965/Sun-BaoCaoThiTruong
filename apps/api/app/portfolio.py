"""Manual, read-only portfolio accounting independent of brokerage credentials."""

import csv
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import (
    PortfolioRecord,
    PortfolioTransactionRecord,
    PriceObservation,
    SecurityRecord,
    SessionLocal,
)
from app.schemas import (
    PortfolioCreate,
    PortfolioImportResult,
    PortfolioPosition,
    PortfolioSummary,
    PortfolioTransactionInput,
)


def create_portfolio(payload: PortfolioCreate) -> PortfolioRecord:
    with SessionLocal() as session:
        row = PortfolioRecord(
            name=payload.name.strip(),
            base_currency=payload.base_currency.strip().upper(),
            created_at=datetime.now(UTC),
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ValueError("Portfolio name already exists") from exc
        session.refresh(row)
        session.expunge(row)
        return row


def _current_quantity(session, portfolio_id: int, symbol: str) -> Decimal:
    rows = session.scalars(
        select(PortfolioTransactionRecord).where(
            PortfolioTransactionRecord.portfolio_id == portfolio_id,
            PortfolioTransactionRecord.symbol == symbol,
        )
    ).all()
    return sum(
        (
            row.quantity
            if row.transaction_type == "buy"
            else -row.quantity if row.transaction_type == "sell" else Decimal(0)
        )
        for row in rows
    )


def add_transaction(portfolio_id: int, payload: PortfolioTransactionInput) -> tuple[object, bool]:
    with SessionLocal() as session:
        if session.get(PortfolioRecord, portfolio_id) is None:
            raise LookupError("Portfolio không tồn tại")
        symbol = payload.symbol.strip().upper()
        if session.scalar(select(SecurityRecord.id).where(SecurityRecord.symbol == symbol)) is None:
            raise ValueError(f"Mã {symbol} chưa có trong securities master")
        existing = session.scalar(
            select(PortfolioTransactionRecord).where(
                PortfolioTransactionRecord.portfolio_id == portfolio_id,
                PortfolioTransactionRecord.external_id == payload.external_id,
            )
        )
        if existing is not None:
            session.expunge(existing)
            return existing, False
        if payload.transaction_type == "sell" and Decimal(str(payload.quantity)) > _current_quantity(
            session, portfolio_id, symbol
        ):
            raise ValueError("Sell quantity exceeds current holding")
        row = PortfolioTransactionRecord(
            portfolio_id=portfolio_id,
            symbol=symbol,
            transaction_type=payload.transaction_type,
            quantity=Decimal(str(payload.quantity)),
            price=Decimal(str(payload.price)),
            fees=Decimal(str(payload.fees)),
            cash_amount=Decimal(str(payload.cash_amount)),
            executed_at=payload.executed_at.astimezone(UTC),
            external_id=payload.external_id,
            source_name=payload.source_name,
            created_at=datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row, True


def import_transactions_csv(
    portfolio_id: int, content: str, source_name: str
) -> PortfolioImportResult:
    inserted = skipped = rejected = 0
    errors = []
    for line_number, row in enumerate(csv.DictReader(StringIO(content)), start=2):
        try:
            payload = PortfolioTransactionInput(
                symbol=row.get("symbol", ""),
                transaction_type=row.get("transaction_type", ""),
                quantity=float(row.get("quantity") or 0),
                price=float(row.get("price") or 0),
                fees=float(row.get("fees") or 0),
                cash_amount=float(row.get("cash_amount") or 0),
                executed_at=datetime.fromisoformat(row.get("executed_at") or ""),
                external_id=row.get("external_id", ""),
                source_name=(row.get("source_name") or source_name)[:128],
            )
            _, was_inserted = add_transaction(portfolio_id, payload)
            inserted += int(was_inserted)
            skipped += int(not was_inserted)
        except (LookupError, TypeError, ValueError, ValidationError) as exc:
            rejected += 1
            errors.append(f"line {line_number}: {exc}")
    return PortfolioImportResult(
        inserted=inserted, skipped=skipped, rejected=rejected, errors=errors[:100]
    )


def portfolio_summary(portfolio_id: int) -> PortfolioSummary:
    with SessionLocal() as session:
        portfolio = session.get(PortfolioRecord, portfolio_id)
        if portfolio is None:
            raise LookupError("Portfolio không tồn tại")
        transactions = session.scalars(
            select(PortfolioTransactionRecord)
            .where(PortfolioTransactionRecord.portfolio_id == portfolio_id)
            .order_by(
                PortfolioTransactionRecord.executed_at,
                PortfolioTransactionRecord.id,
            )
        ).all()
        states = defaultdict(
            lambda: {"quantity": Decimal(0), "cost": Decimal(0), "realized": Decimal(0)}
        )
        for row in transactions:
            state = states[row.symbol]
            if row.transaction_type == "buy":
                state["quantity"] += row.quantity
                state["cost"] += row.quantity * row.price + row.fees
            elif row.transaction_type == "sell":
                average = state["cost"] / state["quantity"]
                state["realized"] += row.quantity * row.price - row.fees - average * row.quantity
                state["quantity"] -= row.quantity
                state["cost"] -= average * row.quantity
            else:
                state["realized"] += row.cash_amount

        positions = []
        missing_prices = []
        for symbol, state in sorted(states.items()):
            if state["quantity"] <= 0:
                continue
            security = session.scalar(
                select(SecurityRecord).where(SecurityRecord.symbol == symbol)
            )
            latest = session.scalar(
                select(PriceObservation)
                .where(PriceObservation.security_id == security.id)
                .order_by(PriceObservation.market_timestamp.desc())
            )
            latest_price = float(latest.close) if latest else None
            market_value = (
                float(state["quantity"]) * latest_price if latest_price is not None else None
            )
            if latest_price is None:
                missing_prices.append(symbol)
            positions.append(
                PortfolioPosition(
                    symbol=symbol,
                    sector=security.sector,
                    quantity=float(state["quantity"]),
                    average_cost=float(state["cost"] / state["quantity"]),
                    cost_basis=float(state["cost"]),
                    latest_price=latest_price,
                    market_value=market_value,
                    unrealized_pnl=(market_value - float(state["cost"])) if market_value else None,
                    realized_pnl=float(state["realized"]),
                )
            )
        total_cost = sum(item.cost_basis for item in positions)
        all_priced = bool(positions) and not missing_prices
        total_market = sum(item.market_value or 0 for item in positions) if all_priced else None
        allocation_base = total_market if total_market is not None else total_cost
        sector_values = defaultdict(float)
        weights = []
        if allocation_base > 0:
            for item in positions:
                value = item.market_value if all_priced else item.cost_basis
                item.weight_percent = round(value / allocation_base * 100, 4)
                weights.append(value / allocation_base)
                sector_values[item.sector or "Unclassified"] += value
        limitations = []
        if missing_prices:
            limitations.append(
                "Thiếu giá gần nhất cho: " + ", ".join(missing_prices) + "; phân bổ dùng giá vốn."
            )
        limitations.append("Portfolio là sổ thủ công/CSV; không đồng bộ hoặc giao dịch qua VPS.")
        return PortfolioSummary(
            id=portfolio.id,
            name=portfolio.name,
            base_currency=portfolio.base_currency,
            positions=positions,
            total_cost_basis=round(total_cost, 4),
            total_market_value=round(total_market, 4) if total_market is not None else None,
            realized_pnl=round(sum(float(state["realized"]) for state in states.values()), 4),
            unrealized_pnl=(
                round(total_market - total_cost, 4) if total_market is not None else None
            ),
            sector_allocation_percent={
                sector: round(value / allocation_base * 100, 4)
                for sector, value in sector_values.items()
            }
            if allocation_base > 0
            else {},
            concentration_percent=round(max(weights) * 100, 4) if weights else None,
            herfindahl_index=round(sum(weight * weight for weight in weights), 6)
            if weights
            else None,
            limitations=limitations,
            calculated_at=datetime.now(UTC),
        )
