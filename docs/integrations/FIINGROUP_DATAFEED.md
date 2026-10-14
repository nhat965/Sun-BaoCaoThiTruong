# FiinGroup Datafeed operator setup

FiinGroup documents enterprise APIs for securities data and financial statements,
including original report files and consolidated/separate reporting variants. The
application deliberately does not guess a URL, request body, or field mapping from
the public landing page.

To enable a provider, the operator must supply a contract-approved base URL,
credential, entitlement scope, response example, rate limit and redistribution
terms. Until those artifacts are recorded and a real request succeeds, the catalog
must show `BLOCKED`; an API key by itself is not evidence of data availability.

The authorized financial CSV import remains the supported fallback for files the
operator is permitted to use. Every imported period keeps its source, retrieval
timestamp, reporting scope, unit and validation status.
