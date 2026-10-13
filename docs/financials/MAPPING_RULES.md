# Financial line-item and period mapping rules (PR-A)

1. Provider labels are normalized with Unicode-aware Vietnamese transliteration
   (`đ` is mapped to `d`) and punctuation is converted to underscores.
2. Known aliases map to one canonical item code. Unknown codes remain present
   as stable tokens and retain their raw label.
3. The mapper does not infer a parent-company profit from total net income.
   `net_income` and `net_income_attributable_to_parent` are separate codes.
4. `quarter`, `year`, `ytd` and `ttm` are distinct period types. YTD is never
   treated as an independent quarter.
5. A standalone quarter derived from cumulative YTD is `current_ytd - prior_ytd`
   only when both values belong to the same fiscal year, scope and statement
   version. The conversion helper returns the current YTD unchanged when no
   prior cumulative value exists, leaving the limitation to the caller.
6. TTM period boundaries are not invented. They must be supplied by the source
   or remain null until a later engine can reconcile the four underlying
   quarters.
7. Currency must be a three-letter code. VND-scale units must use VND; shares
   and ratios are not silently converted to monetary units.
8. Every import records the payload hash and retrieval timestamp. A replay of
   identical content remains idempotent and does not require a new timestamp.

