# Financial API and UI contract

`GET /api/v1/stocks/{symbol}/fundamentals` returns the latest persisted
calculation, including `formula_version`, statement period/source metadata and
`metric_metadata` for every metric. Each metadata record distinguishes
`complete`, `incomplete` and `not_applicable` inputs. The history endpoint
returns the same contract for each selected period.

The web research view renders these fields directly: missing values are shown
as **Chưa có dữ liệu**, unavailable financial-entity ratios are labeled **Không
áp dụng**, and incomplete formulas list the missing input names. Tooltips expose
the formula limitation, while the provenance strip shows formula version,
calculation time, statement period and source. The statement ledger keeps
source/unit/status for each normalized line item and does not fabricate a value
when an item is absent.
