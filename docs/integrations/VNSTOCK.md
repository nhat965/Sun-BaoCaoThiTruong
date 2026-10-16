# Vnstock v5 market-data adapter

The API supports `vnstock` as an optional market-data provider for securities
metadata, daily equity OHLCV and daily index observations. The default priority
is `vnstock,ssi_fastconnect,yahoo`; a failed Vnstock request falls through to
the configured providers while keeping the fallback provenance intact.

## Install and configure

Vnstock is optional so CSV imports, fixtures and the SSI adapter remain usable
without it. Install it from the official Vnstock package index:

```powershell
python -m pip install -e ".[vnstock]" --extra-index-url https://vnstocks.com/api/packages
vnstock register
vnstock status
```

Set the selected routes in `.env`:

```dotenv
MARKET_PROVIDER_PRIORITY=vnstock,ssi_fastconnect,yahoo
VNSTOCK_MARKET_SOURCE=vci
VNSTOCK_REFERENCE_SOURCE=vci
```

The adapter calls the documented v5 `Market().equity(symbol).ohlcv()`,
`Market().index(symbol).ohlcv()` and
`Reference().equity.list_by_exchange()` surfaces. Vnstock's documented equity
prices are in thousand VND, so the adapter converts them to the application's
VND `PriceSeries` unit and records that policy in code. Invalid rows and
duplicate timestamps are dropped. Trading value is left null unless the
upstream response explicitly contains it. Equity bars are marked
provider-adjusted, while independent corporate-action verification remains
out of scope.

## Entitlement and data-status rules

Vnstock is a client library, not a data provider. The selected upstream source
must be permitted for the operator's use and redistribution. The API reports a
provider as `configured` until a real request is successful, and `blocked` when
the optional package or registration is missing. No live Vnstock claim is made
from a fixture, a cached Yahoo response, or a package import alone.

Historical acceptance on 2026-10-15 verified a Community credential and live
OHLCV batches of 5, 20 and 50 symbols. The persisted coverage snapshot is 52
symbols with 21,670 bars out of 1,520 active securities (one symbol was already
present before the batch audit). A subsequent CLI check currently reports Guest /
unauthenticated, so no new batch is permitted until the credential is registered
again. The persisted result is delayed daily data, not realtime/full-market
coverage. Use
`apps/api/scripts/vnstock_backfill.py` for checkpointed batches and
`apps/api/scripts/vnstock_coverage.py` for read-only coverage checks.

The installed SDK also exposes `Fundamental().equity(symbol).income_statement`,
`balance_sheet` and `cash_flow`. The API now maps the documented level-1 VAS
rows for a read-only HPG (and other symbol) fallback. The result is explicitly
marked `LIVE`, `unverified`, includes provider/source/timestamp provenance and
is not written to canonical financial tables. The Community tier still limits
the response to the latest eight periods; statement scope and period-end
semantics follow the provider default and must be independently validated before
an authorized import is promoted to `verified`.

## Community free-surface integration

The API now exposes a read-only, named allow-list for the Vnstock v5 Community
surfaces. It is intentionally separate from the canonical OHLCV/financial
tables: the response is returned with `source`, `route`, `retrieved_at` and a
`persisted=false` provenance marker until the upstream schema, unit and
reporting scope have been validated.

```text
GET /api/v1/vnstock/free/catalog
GET /api/v1/vnstock/free/{operation}?symbol=HPG&period=quarter&limit=100
```

The catalog response includes the six documented free-source identifiers:
`vci`, `kbs`, `builtin`, `binance`, `dukascopy` and `vcb`, with the data group
and entitlement for each source.

The catalog includes the documented free groups: reference (company/listing,
industry, index, ETF/futures/warrant/bond lists and events), market (equity,
index, futures, warrant, ETF and bond quote/OHLCV/trades, multi-symbol quote,
and the documented global instrument OHLCV surfaces), and Fundamental income
statement, balance sheet and cash flow. Community market requests are limited
to permitted domestic routes (`vci`/`kbs`) by the official documentation.

Insights, Macro, Analytics valuation, ratios and flow/order-book extensions are
shown in the catalog as `blocked_without_entitlement`; the gateway will never
call them under a Community account. A provider error is returned as
`BLOCKED` or `FAILED` with a stable error code, and raw exceptions or secrets
are not returned.

The endpoint is an integration/diagnostic boundary, not a claim of full-market
coverage. A live backend probe has succeeded for HPG with source `vci`; the
local CLI may still report Guest/unauthenticated when its profile differs from
the running backend, so credentials and entitlement must be re-verified before
batch ingestion or publication.

The free catalog also includes `reference.search_symbol`, index descriptions,
and `retail.exchange_rate` (Vietcombank). Financial statements accept
`period=year|quarter` and `format=long|wide|time_series`; the Community tier is
limited to the most recent eight periods and the reduced level-1 VAS set.
`ratio`, `note`, `financial_health`, annual plans and single derivative/bond
information remain visible as blocked capability entries because the official
free documentation assigns them to Expanded or Sponsor access. See the
[Community reference matrix](https://vnstocks.com/docs/vnstock/free/tham-chieu-reference),
[Community market matrix](https://vnstocks.com/docs/vnstock/free/thi-truong-market),
[Community fundamental matrix](https://vnstocks.com/docs/vnstock/free/co-ban-fundamental)
and [Retail documentation](https://vnstocks.com/docs/vnstock/hang-hoa-ban-le-retail)
for the source and tier rules.

Source routing is explicit: domestic equity/financial/reference requests use
`vci` or `kbs`; crypto uses `binance`; forex, commodities and global indices
use `dukascopy`; local market calendars use `builtin`; Retail uses `vcb`.
The gateway does not silently fall back between sources.
