# FiinGroup financial provider boundary

FiinGroup documentation confirms financial-statement capability, including original
report files and consolidated/separate variants. The application does not infer a
production URL or response schema from that documentation. `FIINGROUP_FINANCIAL_ENDPOINT_TEMPLATE`,
the API key, and an explicit rights confirmation are required. The fetcher remains
injected until the contract-approved response mapping is recorded; otherwise calls
return `BLOCKED` and no financial period is written.
