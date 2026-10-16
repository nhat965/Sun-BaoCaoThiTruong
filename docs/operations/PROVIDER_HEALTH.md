# Provider health

`GET /api/v1/sources/status` and `GET /api/v1/providers` expose the persisted provider
catalog. `POST /api/v1/admin/providers/health-check` records a diagnostic scheduler run.
Health state is evidence-based: `available` requires a successful persisted sync,
`configured` means credentials/contract fields exist but a live call is not proven,
`blocked` identifies missing credentials, endpoint or rights, and `fixture` is development
only. A blocked source is skipped by the worker and has an error code rather than an
infinite retry loop.

Current production gaps remain SSI entitlement, FireAnt scopes and FiinGroup contract/API
rights. The authorized CSV path is available only when an operator supplies provenance and
confirms permitted use.
