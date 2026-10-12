# V4 security review

## Verified controls

- Persistent imports, valuation writes, job writes, watchlists and alert rules require the admin bearer role.
- The public valuation endpoint is calculation-only.
- Request body size, Pydantic field limits, CSV size limits and analyst question limits are enforced.
- Admin and analyst requests are rate-limited; audit metadata excludes tokens and only records symbol/question length for analyst calls.
- Trusted hosts and CORS are configured; production settings reject missing/weak admin credentials and wildcard hosts.
- External news text is treated as untrusted metadata and never executed.

## Remaining risks

- The MVP token is not a multi-user identity/ownership system.
- Rate limiting is process-local and must move to a shared backend for multiple workers.
- Dependency scanning and penetration testing were not executable in the restricted environment.
- Provider licensing and OAuth scope verification remain external gates.
