# Market report schema

Pre-market and post-market snapshots are generated from the same persisted engines as the API dashboard. The `sections` object includes `breadth`, `regime`, `liquidity`, `risks`, `scenarios`, `sectors` (post-market), `provenance`, and `limitations`.

Every statement is built from the selected session's response and carries an explicit source/as-of/status line. A missing provider value remains missing; reports do not infer foreign flow, trading value, probabilities, or price targets. Snapshot keys are deterministic per report type and trading date, so retries update one row instead of creating duplicates.
