# Technical analysis formula notes

All calculations use validated, ascending daily OHLCV and formula version `technical-v2`.

- Trend score (0–100): starts at 50; close versus SMA20 and SMA20 versus SMA50 each contribute ±15; ADX contributes up to ±20 in the +DI/-DI direction.
- Momentum score (0–100): RSI displacement contributes 0.5 per point, 12-period ROC is capped at ±20 after a ×2 scaling, and MACD histogram contributes ±10.
- Volume-confirmation score (0–100): CMF contributes ×40, MFI displacement contributes ×0.3, and relative volume ≥1.2 adds or subtracts 8 according to CMF direction.
- Volatility-risk score (0–100): `1.2 × annualized volatility + 1.5 × |max drawdown| + 3 × ATR/close%`, bounded to 0–100. Higher means more risk, not a bullish signal.

Supporting indicators include EMA, RSI, MACD, Bollinger Bands, ATR, OBV, maximum drawdown, ADX/+DI/-DI, Stochastic, Stochastic RSI, ROC, historical volatility, MFI, CMF, relative volume and 20-session support/resistance. Missing history produces `unavailable`; no value is invented. A flat RSI series is defined as 50.

The engine reports explicit conflicts when trend, momentum or volume confirmation disagree. These scores describe historical data and are not investment advice.
