# AI analyst architecture

The analyst is a thin orchestration layer over deterministic tools. Price, technical, fundamental and valuation numbers are calculated by Python services and passed to the optional language provider as evidence. External titles and excerpts are untrusted data and are delimited as evidence; they cannot invoke tools.

`POST /api/v1/analyst/chat` validates the symbol/question, applies an IP rate limit, records secret-free audit metadata and returns typed sections plus evidence records. Without complete `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` and `LLM_BASE_URL`, the endpoint returns a deterministic Vietnamese fallback and explicitly reports the missing capability.

The OpenAI-compatible adapter uses a short timeout, temperature zero and no secret logging. Claim verification remains a next slice: generated numeric claims must be checked against evidence before being promoted to a production report.
