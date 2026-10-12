# AI analyst architecture

The analyst is a thin orchestration layer over deterministic tools. Price, technical, fundamental and valuation numbers are calculated by Python services and passed to the optional language provider as evidence. External titles and excerpts are untrusted data and are delimited as evidence; they cannot invoke tools.

`POST /api/v1/analyst/chat` validates the symbol/question, applies an IP rate limit, records secret-free audit metadata and returns typed sections plus evidence records. Without complete `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` and `LLM_BASE_URL`, the endpoint returns a deterministic Vietnamese fallback and explicitly reports the missing capability.

The OpenAI-compatible adapter uses a short timeout, temperature zero and no secret logging. Evidence records receive stable response-local IDs (`E001`, `E002`, ...). Generated answers must cite known evidence IDs and every numeric token must match a value in deterministic tool outputs within a narrow tolerance. Answers that fail either check are discarded and replaced by the deterministic Vietnamese fallback; verification reasons are exposed as limitations.

The verifier is intentionally conservative. Production evaluation must still expand semantic validation for dates, named events and paraphrased claims before M5 can be marked complete.
