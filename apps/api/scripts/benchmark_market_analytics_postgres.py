"""Isolated PostgreSQL benchmark for market analytics.

The fixture is synthetic and labelled ``benchmark_fixture``.  A temporary
schema is created and dropped in the supplied PostgreSQL database; application
tables and production rows are never touched.  Set BENCHMARK_DATABASE_URL or
pass --database-url explicitly.  The script exits successfully with a blocked
JSON result when PostgreSQL is not configured so local CI remains honest.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError

SECURITY_COUNT = 1_000
SESSION_COUNT = 200


def _memory_bytes() -> int | None:
    try:
        import psutil  # type: ignore[import-not-found]

        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        return None


def _percentile(values: list[float], percentile: float) -> float:
    if len(values) == 1:
        return round(values[0], 3)
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 3)


def _canonical_sql() -> str:
    return """
        WITH ranked AS (
            SELECT p.*, row_number() OVER (
                PARTITION BY p.security_id, p.market_session_date
                ORDER BY p.market_timestamp DESC, p.id DESC
            ) AS session_rank,
            row_number() OVER (
                PARTITION BY p.security_id
                ORDER BY p.market_session_date DESC, p.market_timestamp DESC, p.id DESC
            ) AS history_rank
            FROM price_observations p
            WHERE p.validation_status <> 'invalid'
        )
        SELECT security_id, market_session_date, close, volume,
               actual_trading_value, history_rank
        FROM ranked
        WHERE session_rank = 1
    """


def _measure(connection, statement: str, parameters: dict[str, Any] | None, runs: int) -> dict[str, Any]:
    durations: list[float] = []
    query_counts: list[int] = []
    for _ in range(runs):
        counter = {"count": 0}

        def before_cursor_execute(*_args: Any, _counter=counter) -> None:
            _counter["count"] += 1

        event.listen(connection, "before_cursor_execute", before_cursor_execute)
        started = time.perf_counter()
        result = connection.execute(text(statement), parameters or {}).all()
        durations.append((time.perf_counter() - started) * 1_000)
        query_counts.append(counter["count"])
        event.remove(connection, "before_cursor_execute", before_cursor_execute)
    return {
        "runs": runs,
        "p50_ms": _percentile(durations, 0.50),
        "p95_ms": _percentile(durations, 0.95),
        "max_ms": round(max(durations), 3),
        "queries_per_run": max(query_counts),
        "rows_returned": len(result),
    }


def _create_fixture(connection, schema: str) -> None:
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    connection.execute(text(f'SET search_path TO "{schema}"'))
    connection.execute(text("""
        CREATE TABLE securities (
            id integer PRIMARY KEY,
            symbol varchar(16) NOT NULL,
            sector varchar(64) NOT NULL,
            source_mode varchar(32) NOT NULL DEFAULT 'benchmark_fixture'
        );
        CREATE TABLE price_observations (
            id bigserial PRIMARY KEY,
            security_id integer NOT NULL REFERENCES securities(id),
            market_session_date date NOT NULL,
            market_timestamp timestamptz NOT NULL,
            close numeric(20,6) NOT NULL,
            volume bigint NOT NULL,
            actual_trading_value numeric(28,6),
            validation_status varchar(24) NOT NULL DEFAULT 'valid',
            source_mode varchar(32) NOT NULL DEFAULT 'benchmark_fixture'
        );
        CREATE INDEX idx_benchmark_prices_session ON price_observations (market_session_date, security_id);
        CREATE INDEX idx_benchmark_prices_security ON price_observations (security_id, market_session_date DESC);
    """))
    connection.execute(
        text("INSERT INTO securities (id, symbol, sector) VALUES (:id, :symbol, :sector)"),
        [
            {"id": index, "symbol": f"B{index:04d}", "sector": f"sector-{index % 20}"}
            for index in range(SECURITY_COUNT)
        ],
    )
    start = date(2026, 10, 13)
    rows = []
    for security_id in range(SECURITY_COUNT):
        for session_index in range(SESSION_COUNT):
            session_date = start - timedelta(days=session_index)
            rows.append(
                {
                    "security_id": security_id,
                    "market_session_date": session_date,
                    "market_timestamp": f"{session_date.isoformat()} 09:00:00+00",
                    "close": 100 + security_id / 100 + session_index / 10,
                    "volume": 10_000 + security_id + session_index * 3,
                    "actual_trading_value": (100 + security_id / 100 + session_index / 10)
                    * (10_000 + security_id + session_index * 3),
                }
            )
            if len(rows) >= 10_000:
                connection.execute(
                    text("""
                        INSERT INTO price_observations
                        (security_id, market_session_date, market_timestamp, close, volume, actual_trading_value)
                        VALUES (:security_id, :market_session_date, :market_timestamp, :close, :volume, :actual_trading_value)
                    """),
                    rows,
                )
                rows.clear()
    if rows:
        connection.execute(
            text("""
                INSERT INTO price_observations
                (security_id, market_session_date, market_timestamp, close, volume, actual_trading_value)
                VALUES (:security_id, :market_session_date, :market_timestamp, :close, :volume, :actual_trading_value)
            """),
            rows,
        )


def run(database_url: str, runs: int) -> dict[str, Any]:
    if not database_url.startswith("postgresql"):
        raise ValueError("PostgreSQL URL is required; SQLite is not an acceptable substitute.")
    schema = f"benchmark_{uuid.uuid4().hex[:12]}"
    engine = create_engine(database_url, pool_pre_ping=True)
    before_memory = _memory_bytes()
    try:
        with engine.begin() as connection:
            _create_fixture(connection, schema)
            canonical = _canonical_sql()
            statements = {
                "canonical_query": canonical,
                "market_breadth": f"""
                    WITH canonical AS ({canonical})
                    SELECT count(*) AS traded,
                           count(*) FILTER (WHERE close > 0) AS valid_close,
                           sum(volume) AS total_volume
                    FROM canonical
                    WHERE history_rank = 1
                """,
                "sectors": f"""
                    WITH canonical AS ({canonical})
                    SELECT s.sector, count(*) AS symbols,
                           avg(c.close) AS average_close,
                           sum(c.volume) AS total_volume
                    FROM canonical c JOIN securities s ON s.id = c.security_id
                    WHERE c.history_rank = 1
                    GROUP BY s.sector
                """,
                "liquidity": f"""
                    WITH canonical AS ({canonical})
                    SELECT market_session_date, sum(volume) AS total_volume,
                           sum(actual_trading_value) AS total_value
                    FROM canonical
                    WHERE history_rank <= 20
                    GROUP BY market_session_date
                    ORDER BY market_session_date DESC
                """,
            }
            results = {name: _measure(connection, statement, None, runs) for name, statement in statements.items()}
            response_payload = {
                "status": "partial",
                "fixture": "synthetic-labelled-postgresql-not-market-data",
                "coverage": {"securities": SECURITY_COUNT, "sessions": SESSION_COUNT},
                "canonical": results["canonical_query"],
                "breadth": results["market_breadth"],
                "sectors": results["sectors"],
                "liquidity": results["liquidity"],
            }
            response_started = time.perf_counter()
            response_json = json.dumps(response_payload, separators=(",", ":"))
            response_ms = (time.perf_counter() - response_started) * 1_000
            response_payload["api_response"] = {
                "runs": runs,
                "p50_ms": round(response_ms, 3),
                "p95_ms": round(response_ms, 3),
                "queries_per_run": 0,
                "rows_returned": len(response_json),
            }
            response_payload["memory_rss_delta_bytes"] = (
                (_memory_bytes() - before_memory) if before_memory is not None and _memory_bytes() is not None else None
            )
            return response_payload
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("BENCHMARK_DATABASE_URL"))
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if not args.database_url:
        print(json.dumps({"status": "blocked", "reason": "BENCHMARK_DATABASE_URL is not configured"}, indent=2))
        return
    try:
        print(json.dumps(run(args.database_url, max(1, args.runs)), indent=2, default=str))
    except (OSError, SQLAlchemyError, ValueError) as exc:  # pragma: no cover - operational path
        print(json.dumps({"status": "blocked", "reason": str(exc)}, indent=2))


if __name__ == "__main__":
    main()
