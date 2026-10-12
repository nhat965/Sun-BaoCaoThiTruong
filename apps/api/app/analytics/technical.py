from datetime import UTC, datetime
from itertools import pairwise
from math import sqrt

from app.schemas import IndicatorValue, PriceBar, TechnicalSnapshot


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def sma(values: list[float], period: int) -> float | None:
    return None if len(values) < period else sum(values[-period:]) / period


def ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    seed = sum(values[:period]) / period
    result = [seed]
    multiplier = 2 / (period + 1)
    for value in values[period:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def ema(values: list[float], period: int) -> float | None:
    series = ema_series(values, period)
    return series[-1] if series else None


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [current - previous for previous, current in pairwise(values)]
    gains = [max(change, 0) for change in changes]
    losses = [max(-change, 0) for change in changes]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period
    if average_loss == 0 and average_gain == 0:
        return 50.0
    if average_loss == 0:
        return 100.0
    return 100 - 100 / (1 + average_gain / average_loss)


def macd(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if len(values) < 35:
        return None, None, None
    line = []
    for end in range(26, len(values) + 1):
        fast = ema(values[:end], 12)
        slow = ema(values[:end], 26)
        if fast is not None and slow is not None:
            line.append(fast - slow)
    signal = ema(line, 9)
    return line[-1], signal, None if signal is None else line[-1] - signal


def bollinger(
    values: list[float], period: int = 20, deviations: float = 2
) -> tuple[float | None, float | None, float | None]:
    middle = sma(values, period)
    if middle is None:
        return None, None, None
    sample = values[-period:]
    std = sqrt(sum((value - middle) ** 2 for value in sample) / period)
    return middle - deviations * std, middle, middle + deviations * std


def atr(bars: list[PriceBar], period: int = 14) -> float | None:
    if len(bars) <= period:
        return None
    ranges = []
    for previous, current in pairwise(bars):
        ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    value = sum(ranges[:period]) / period
    for current in ranges[period:]:
        value = (value * (period - 1) + current) / period
    return value


def obv(bars: list[PriceBar]) -> int | None:
    if not bars:
        return None
    value = 0
    for previous, current in pairwise(bars):
        value += (
            current.volume
            if current.close > previous.close
            else -current.volume
            if current.close < previous.close
            else 0
        )
    return value


def maximum_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst * 100


def percentage_change(current: float, previous: float) -> float | None:
    return None if previous == 0 else (current - previous) / previous * 100


def roc(values: list[float], period: int = 12) -> float | None:
    if len(values) <= period or values[-period - 1] == 0:
        return None
    return (values[-1] / values[-period - 1] - 1) * 100


def stochastic(
    bars: list[PriceBar], period: int = 14, smooth: int = 3
) -> tuple[float | None, float | None]:
    if len(bars) < period + smooth - 1:
        return None, None
    k_values = []
    for end in range(period, len(bars) + 1):
        sample = bars[end - period : end]
        low = min(item.low for item in sample)
        high = max(item.high for item in sample)
        k_values.append(50.0 if high == low else (sample[-1].close - low) / (high - low) * 100)
    return k_values[-1], sma(k_values, smooth)


def stochastic_rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period * 2 + 1:
        return None
    rsi_values = [rsi(values[:end], period) for end in range(period + 1, len(values) + 1)]
    usable = [item for item in rsi_values if item is not None]
    if len(usable) < period:
        return None
    sample = usable[-period:]
    low, high = min(sample), max(sample)
    return 50.0 if high == low else (sample[-1] - low) / (high - low) * 100


def historical_volatility(values: list[float], period: int = 20) -> float | None:
    if len(values) <= period:
        return None
    returns = [current / previous - 1 for previous, current in pairwise(values[-period - 1 :])]
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / max(1, len(returns) - 1)
    return sqrt(variance) * sqrt(252) * 100


def adx(bars: list[PriceBar], period: int = 14) -> tuple[float | None, float | None, float | None]:
    if len(bars) < period * 2 + 1:
        return None, None, None
    true_ranges, plus_dm, minus_dm = [], [], []
    for previous, current in pairwise(bars):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
        up, down = current.high - previous.high, previous.low - current.low
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
    atr_value = sum(true_ranges[:period])
    plus_value = sum(plus_dm[:period])
    minus_value = sum(minus_dm[:period])
    dx_values = []
    plus_di = minus_di = 0.0
    for index in range(period, len(true_ranges)):
        atr_value = atr_value - atr_value / period + true_ranges[index]
        plus_value = plus_value - plus_value / period + plus_dm[index]
        minus_value = minus_value - minus_value / period + minus_dm[index]
        if atr_value == 0:
            continue
        plus_di, minus_di = 100 * plus_value / atr_value, 100 * minus_value / atr_value
        denominator = plus_di + minus_di
        dx_values.append(0 if denominator == 0 else 100 * abs(plus_di - minus_di) / denominator)
    return sma(dx_values, period), plus_di, minus_di


def mfi(bars: list[PriceBar], period: int = 14) -> float | None:
    if len(bars) <= period:
        return None
    flows = []
    for previous, current in pairwise(bars[-period - 1 :]):
        previous_typical = (previous.high + previous.low + previous.close) / 3
        typical = (current.high + current.low + current.close) / 3
        flow = typical * current.volume
        flows.append(
            (flow if typical > previous_typical else 0, flow if typical < previous_typical else 0)
        )
    positive, negative = sum(item[0] for item in flows), sum(item[1] for item in flows)
    if negative == 0:
        return 100.0
    return 100 - 100 / (1 + positive / negative)


def cmf(bars: list[PriceBar], period: int = 20) -> float | None:
    if len(bars) < period:
        return None
    money_flow_volume = volume = 0.0
    for bar in bars[-period:]:
        spread = bar.high - bar.low
        multiplier = 0 if spread == 0 else ((bar.close - bar.low) - (bar.high - bar.close)) / spread
        money_flow_volume += multiplier * bar.volume
        volume += bar.volume
    return None if volume == 0 else money_flow_volume / volume


def relative_volume(bars: list[PriceBar], period: int = 20) -> float | None:
    if len(bars) <= period:
        return None
    baseline = sum(item.volume for item in bars[-period - 1 : -1]) / period
    return None if baseline == 0 else bars[-1].volume / baseline


def support_resistance(bars: list[PriceBar], period: int = 20) -> tuple[float | None, float | None]:
    if len(bars) < period:
        return None, None
    sample = bars[-period:]
    return min(item.low for item in sample), max(item.high for item in sample)


def _bounded(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def component_scores(
    bars: list[PriceBar], indicators: dict[str, IndicatorValue]
) -> tuple[dict[str, float | None], list[str]]:
    latest = bars[-1].close
    sma20_value = indicators["sma20"].value
    sma50_value = indicators["sma50"].value
    adx_value = indicators["adx14"].value
    plus_di = indicators["plus_di14"].value
    minus_di = indicators["minus_di14"].value
    trend = None
    if sma20_value is not None and sma50_value is not None:
        trend = 50.0
        trend += 15 if latest >= sma20_value else -15
        trend += 15 if sma20_value >= sma50_value else -15
        if adx_value is not None and plus_di is not None and minus_di is not None:
            directional = 1 if plus_di >= minus_di else -1
            trend += directional * min(20, adx_value / 2)
        trend = _bounded(trend)

    rsi_value = indicators["rsi14"].value
    roc_value = indicators["roc12"].value
    histogram = indicators["macd_histogram"].value
    momentum = None
    if rsi_value is not None and roc_value is not None and histogram is not None:
        momentum = _bounded(50 + (rsi_value - 50) * 0.5 + max(-20, min(20, roc_value * 2)))
        momentum = _bounded(momentum + (10 if histogram >= 0 else -10))

    cmf_value = indicators["cmf20"].value
    mfi_value = indicators["mfi14"].value
    rel_volume = indicators["relative_volume20"].value
    volume_score = None
    if cmf_value is not None and mfi_value is not None and rel_volume is not None:
        volume_score = _bounded(50 + cmf_value * 40 + (mfi_value - 50) * 0.3)
        if rel_volume >= 1.2:
            volume_score = _bounded(volume_score + (8 if cmf_value >= 0 else -8))

    volatility = indicators["historical_volatility20"].value
    drawdown = indicators["max_drawdown"].value
    atr_value = indicators["atr14"].value
    risk = None
    if volatility is not None and drawdown is not None and atr_value is not None and latest > 0:
        risk = _bounded(volatility * 1.2 + abs(drawdown) * 1.5 + atr_value / latest * 100 * 3)

    scores = {
        "trend": _round(trend),
        "momentum": _round(momentum),
        "volume_confirmation": _round(volume_score),
        "volatility_risk": _round(risk),
    }
    conflicts = []
    if trend is not None and momentum is not None:
        if trend >= 60 and momentum <= 40:
            conflicts.append("Xu hướng vẫn tích cực nhưng động lượng đang suy yếu.")
        elif trend <= 40 and momentum >= 60:
            conflicts.append("Động lượng phục hồi nhưng xu hướng nền vẫn yếu.")
    if volume_score is not None and trend is not None and trend >= 60 and volume_score < 45:
        conflicts.append("Xu hướng tăng chưa được xác nhận rõ bởi dòng khối lượng.")
    return scores, conflicts


def _signal(
    value: float | None, positive: bool, positive_text: str, negative_text: str
) -> IndicatorValue:
    if value is None:
        return IndicatorValue(
            value=None, signal="unavailable", explanation="Không đủ lịch sử để tính."
        )
    return IndicatorValue(
        value=_round(value),
        signal="positive" if positive else "negative",
        explanation=positive_text if positive else negative_text,
    )


def calculate_snapshot(bars: list[PriceBar]) -> TechnicalSnapshot:
    closes = [bar.close for bar in bars]
    latest = closes[-1]
    sma20, sma50 = sma(closes, 20), sma(closes, 50)
    rsi14 = rsi(closes)
    macd_line, macd_signal, histogram = macd(closes)
    lower, middle, upper = bollinger(closes)
    atr14 = atr(bars)
    ema20 = ema(closes, 20)
    adx14, plus_di14, minus_di14 = adx(bars)
    stochastic_k, stochastic_d = stochastic(bars)
    stoch_rsi14 = stochastic_rsi(closes)
    roc12 = roc(closes)
    volatility20 = historical_volatility(closes)
    mfi14 = mfi(bars)
    cmf20 = cmf(bars)
    relative_volume20 = relative_volume(bars)
    support20, resistance20 = support_resistance(bars)
    indicators = {
        "sma20": _signal(
            sma20,
            sma20 is not None and latest >= sma20,
            "Giá đóng cửa ở trên SMA20.",
            "Giá đóng cửa ở dưới SMA20.",
        ),
        "sma50": _signal(
            sma50,
            sma50 is not None and latest >= sma50,
            "Giá đóng cửa ở trên SMA50.",
            "Giá đóng cửa ở dưới SMA50.",
        ),
        "ema20": _signal(
            ema20,
            ema20 is not None and latest >= ema20,
            "Giá đóng cửa ở trên EMA20.",
            "Giá đóng cửa ở dưới EMA20.",
        ),
        "rsi14": IndicatorValue(
            value=_round(rsi14),
            signal="unavailable"
            if rsi14 is None
            else "negative"
            if rsi14 > 70
            else "positive"
            if rsi14 < 30
            else "neutral",
            explanation="RSI trên 70: động lượng cao/quá mua."
            if rsi14 and rsi14 > 70
            else "RSI dưới 30: động lượng thấp/quá bán."
            if rsi14 is not None and rsi14 < 30
            else "RSI trong vùng trung tính."
            if rsi14 is not None
            else "Không đủ lịch sử để tính.",
        ),
        "macd": _signal(
            macd_line,
            histogram is not None and histogram >= 0,
            "MACD histogram không âm.",
            "MACD histogram âm.",
        ),
        "macd_signal": IndicatorValue(
            value=_round(macd_signal), signal="neutral", explanation="Đường tín hiệu EMA9 của MACD."
        ),
        "macd_histogram": IndicatorValue(
            value=_round(histogram),
            signal="neutral",
            explanation="Chênh lệch MACD và đường tín hiệu.",
        ),
        "bollinger_lower": IndicatorValue(
            value=_round(lower), signal="neutral", explanation="Dải dưới Bollinger 20,2."
        ),
        "bollinger_middle": IndicatorValue(
            value=_round(middle), signal="neutral", explanation="Trung bình 20 phiên."
        ),
        "bollinger_upper": IndicatorValue(
            value=_round(upper), signal="neutral", explanation="Dải trên Bollinger 20,2."
        ),
        "atr14": IndicatorValue(
            value=_round(atr14), signal="neutral", explanation="Biên độ thực trung bình 14 phiên."
        ),
        "obv": IndicatorValue(
            value=_round(float(obv(bars))) if obv(bars) is not None else None,
            signal="neutral",
            explanation="On-Balance Volume tích lũy.",
        ),
        "max_drawdown": IndicatorValue(
            value=_round(maximum_drawdown(closes)),
            signal="neutral",
            explanation="Mức sụt giảm lớn nhất trong mẫu.",
        ),
        "adx14": IndicatorValue(
            value=_round(adx14), signal="neutral", explanation="Độ mạnh xu hướng Wilder ADX 14."
        ),
        "plus_di14": IndicatorValue(
            value=_round(plus_di14), signal="neutral", explanation="Chỉ báo hướng dương +DI 14."
        ),
        "minus_di14": IndicatorValue(
            value=_round(minus_di14), signal="neutral", explanation="Chỉ báo hướng âm -DI 14."
        ),
        "stochastic_k": IndicatorValue(
            value=_round(stochastic_k), signal="neutral", explanation="Stochastic %K 14 phiên."
        ),
        "stochastic_d": IndicatorValue(
            value=_round(stochastic_d),
            signal="neutral",
            explanation="Trung bình 3 kỳ của Stochastic %K.",
        ),
        "stochastic_rsi14": IndicatorValue(
            value=_round(stoch_rsi14),
            signal="neutral",
            explanation="Vị trí RSI trong biên 14 kỳ gần nhất.",
        ),
        "roc12": IndicatorValue(
            value=_round(roc12), signal="neutral", explanation="Tốc độ thay đổi giá 12 phiên."
        ),
        "historical_volatility20": IndicatorValue(
            value=_round(volatility20),
            signal="neutral",
            explanation="Độ biến động năm hóa từ lợi suất 20 phiên.",
        ),
        "mfi14": IndicatorValue(
            value=_round(mfi14), signal="neutral", explanation="Money Flow Index 14 phiên."
        ),
        "cmf20": IndicatorValue(
            value=_round(cmf20), signal="neutral", explanation="Chaikin Money Flow 20 phiên."
        ),
        "relative_volume20": IndicatorValue(
            value=_round(relative_volume20),
            signal="neutral",
            explanation="Khối lượng phiên cuối so với trung bình 20 phiên trước.",
        ),
        "support20": IndicatorValue(
            value=_round(support20),
            signal="neutral",
            explanation="Đáy thấp nhất trong 20 phiên, chỉ là mức tham chiếu toán học.",
        ),
        "resistance20": IndicatorValue(
            value=_round(resistance20),
            signal="neutral",
            explanation="Đỉnh cao nhất trong 20 phiên, chỉ là mức tham chiếu toán học.",
        ),
    }
    scores, conflicts = component_scores(bars, indicators)
    return TechnicalSnapshot(
        calculated_at=datetime.now(UTC),
        sample_size=len(bars),
        indicators=indicators,
        component_scores=scores,
        conflicts=conflicts,
    )
