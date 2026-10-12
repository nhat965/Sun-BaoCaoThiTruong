import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import enforce_llm_rate_limit, llm_rate_limiter
from app.config import Settings
from app.middleware import RequestBodyLimitMiddleware


async def _call_with_chunks(chunks: list[bytes], max_bytes: int):
    received = []
    sent = []

    async def endpoint(scope, receive, send):
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        received.append(body)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/upload",
        "headers": [],
        "query_string": b"",
    }
    await RequestBodyLimitMiddleware(endpoint, max_bytes)(scope, receive, send)
    return received, sent


def test_streamed_body_is_rejected_without_content_length():
    received, sent = asyncio.run(_call_with_chunks([b"123456", b"789012"], 10))
    assert received == []
    assert sent[0]["status"] == 413


def test_streamed_body_at_limit_is_replayed_unchanged():
    received, sent = asyncio.run(_call_with_chunks([b"12345", b"67890"], 10))
    assert received == [b"1234567890"]
    assert sent[0]["status"] == 204


def test_excessive_llm_requests_are_rate_limited():
    llm_rate_limiter.reset()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/analyst/chat",
            "headers": [],
            "client": ("203.0.113.10", 12345),
        }
    )
    config = Settings(llm_rate_limit_per_minute=1)
    enforce_llm_rate_limit(request, config)
    with pytest.raises(HTTPException) as exc:
        enforce_llm_rate_limit(request, config)
    assert exc.value.status_code == 429
