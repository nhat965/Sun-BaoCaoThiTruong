# SSI FastConnect adapter status

The adapter implements the documented token exchange and a strict OHLCV response
boundary. `SSI_OHLC_ENDPOINT_TEMPLATE` is intentionally empty by default: the
operator must copy the exact URL from an approved SSI contract or Developer Portal
environment. The application does not guess a path or silently fall back to an
undocumented endpoint.

When configured, the adapter keeps the token in memory, sends it as a Bearer token,
parses only rows containing timestamp/OHLC/volume, and records SSI provenance. A
missing credential, missing endpoint, failed token request, or unrecognized response
is `BLOCKED`/failed and does not write a price observation. Live status is only
recorded by `ConnectorManager` after a real request succeeds.
