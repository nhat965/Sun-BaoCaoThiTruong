# Financial Statements Engine V2 acceptance

The automated acceptance test covers both HPG and FPT using an explicitly
authorized CSV fixture (not fabricated market data and not a commercial API):

1. Confirm both symbols resolve in the securities master.
2. Import the same two-line statement payload for each symbol.
3. Replay the exact payload and assert no new statement items are written.
4. Read the fundamentals API and verify `metric_metadata`, period timestamp and
   an explicit incomplete-input state instead of an invented growth rate.

The live-provider requirement remains honestly blocked until an authorized
FireAnt/SSI/FiinGroup credential and data entitlement are supplied. The
automatic sync endpoint returns `BLOCKED` without those settings, and the
provider catalog never marks a configured-only source as operational.
