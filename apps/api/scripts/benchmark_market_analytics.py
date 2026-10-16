"""Benchmark pure market analytics against a labelled synthetic fixture.

This is a performance check only. The generated prices/volumes are not market
data and the script never writes to the application database.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.sector_liquidity import _above_ma, _relative_volume, _return


def main() -> None:
    security_count = 1_000
    session_count = 200
    start = datetime(2026, 10, 14, 2, tzinfo=UTC)
    histories = [
        [
            SimpleNamespace(
                close=100 + security_index * 0.01 + session_index * 0.05,
                volume=10_000 + security_index + session_index * 3,
                market_timestamp=start - timedelta(days=session_index),
            )
            for session_index in range(session_count)
        ]
        for security_index in range(security_count)
    ]

    started = time.perf_counter()
    result_count = 0
    for history in histories:
        result_count += _relative_volume(history) is not None
        result_count += _return(history, 1) is not None
        result_count += _return(history, 20) is not None
        result_count += _above_ma(history, 20) is not None
        result_count += _above_ma(history, 50) is not None
        result_count += _above_ma(history, 200) is not None
    elapsed_ms = round((time.perf_counter() - started) * 1_000, 2)

    print(
        json.dumps(
            {
                "fixture": "synthetic-labelled-not-market-data",
                "securities": security_count,
                "sessions_per_security": session_count,
                "observations": security_count * session_count,
                "analytics_results": result_count,
                "elapsed_ms": elapsed_ms,
                "database_writes": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
