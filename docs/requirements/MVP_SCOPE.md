# MVP scope

## Included

- HPG-first stock search and daily price research workflow.
- Live Yahoo chart connector plus explicit synthetic fixture connector for tests.
- VnExpress RSS news metadata adapter.
- Technical indicator engine and evidence-grounded rule-based summary.
- FastAPI, SQLAlchemy persistence for analysis audit records, Alembic baseline migration.
- Next.js Vietnamese dashboard and PDF export.

## Deferred

Financial-statement ingestion, valuation, social sentiment, VMSS, authenticated users, alerts, portfolio/VPS synchronization, scheduling, and LLM RAG. Deferred pages are not emitted as empty navigation destinations.

## Acceptance

With live upstream access, searching HPG displays recent sourced prices, a chart, indicator values, related headlines, provenance, and a downloadable report. With upstream failure, the application explains the failure without fabricating data.

