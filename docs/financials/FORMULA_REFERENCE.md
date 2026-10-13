# Financial formula reference

The fundamental engine publishes `formula_version = fundamental-v3`. Every
metric response includes a metadata record describing the required inputs,
applicability, period policy, unit and limitations. Missing inputs produce
`null`; the engine never substitutes fabricated values.

| Metric | Formula | Notes |
| --- | --- | --- |
| Revenue growth | `(current revenue - prior revenue) / prior revenue × 100` | Null when the comparison base is not positive. |
| Gross margin | `gross profit / revenue × 100` | Not applicable to banks and other financial entities. |
| ROE / ROA | `net income / average equity/assets × 100` | Falls back to the current balance if no prior balance exists. |
| ROIC | `NOPAT / average(debt + equity - cash) × 100` | Requires operating income, tax inputs and invested capital. |
| EPS | `parent-attributable profit / diluted shares` | Falls back to total net income/basic shares only when preferred inputs are unavailable. |
| Free cash flow | `operating cash flow - abs(CAPEX)` | Provider CAPEX signs are normalized before subtraction. |
| Quick ratio | `(current assets - inventory) / current liabilities` | Not applicable to banks. |
| Cash conversion | `operating cash flow / net income × 100` | Interpret carefully when net income is zero or negative. |

The repository records the source name and statement period alongside persisted
metric rows. A formula result is not evidence that the underlying source is
complete or independently verified; consumers should inspect the metadata and
validation status before making an investment conclusion.
