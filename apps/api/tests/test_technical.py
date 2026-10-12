from datetime import UTC, datetime, timedelta

from app.analytics.technical import (
    atr,
    bollinger,
    ema,
    macd,
    maximum_drawdown,
    mfi,
    obv,
    percentage_change,
    rsi,
    sma,
)
from app.schemas import PriceBar


def bars(closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(
            timestamp=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i),
            open=value - 1,
            high=value + 2,
            low=value - 2,
            close=value,
            volume=100 + i,
        )
        for i, value in enumerate(closes)
    ]


def test_percentage_change_and_moving_averages():
    assert percentage_change(110, 100) == 10
    assert percentage_change(10, 0) is None
    assert sma([1, 2, 3, 4], 3) == 3
    assert round(ema([1, 2, 3, 4, 5], 3), 4) == 4


def test_rsi_reference_extremes():
    assert rsi(list(range(1, 20))) == 100
    assert rsi(list(range(20, 1, -1))) == 0
    assert rsi([10] * 20) == 50


def test_mfi_flat_money_flow_is_neutral():
    assert mfi(bars([10] * 30)) == 50


def test_macd_bollinger_atr_volume_and_drawdown():
    values = [100 + index * 0.5 for index in range(60)]
    line, signal, histogram = macd(values)
    assert line is not None and line > 0
    assert signal is not None and histogram is not None
    lower, middle, upper = bollinger(values)
    assert lower < middle < upper
    sample = bars(values)
    assert atr(sample) == 4
    assert obv(sample) == sum(item.volume for item in sample[1:])
    assert round(maximum_drawdown([100, 120, 90, 108]), 2) == -25


def test_insufficient_history_returns_none():
    assert sma([1, 2], 3) is None
    assert rsi([1, 2], 14) is None
    assert macd([1, 2]) == (None, None, None)
