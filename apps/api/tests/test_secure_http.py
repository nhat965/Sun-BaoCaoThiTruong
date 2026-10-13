import socket

import httpx
import pytest

from app.secure_http import SecureFetchError, fetch_authorized_csv, validate_https_destination


def test_https_destination_rejects_private_resolution(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.4", 443))],
    )
    with pytest.raises(SecureFetchError, match="non-public"):
        validate_https_destination("https://licensed.example/report.csv", {"licensed.example"})


class _Response:
    is_redirect = False

    def __init__(self, chunks):
        self.chunks = chunks
        self.headers = {"content-type": "text/csv"}

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        yield from self.chunks

    def close(self):
        return None


class _Client:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def build_request(self, method, url, headers):
        return httpx.Request(method, url, headers=headers)

    def send(self, request, stream=True):
        return self.response


def test_csv_fetch_stream_cap_and_utf8(monkeypatch):
    monkeypatch.setattr(
        "app.secure_http.validate_https_destination",
        lambda url, allowed_hosts: "licensed.example",
    )
    monkeypatch.setattr(
        "app.secure_http.httpx.Client",
        lambda **kwargs: _Client(_Response([b"symbol,name\n", "HPG,Hòa Phát\n".encode()])),
    )
    csv = fetch_authorized_csv(
        "https://licensed.example/report.csv",
        allowed_hosts={"licensed.example"},
        bearer_token="secret-token",
        timeout_seconds=1,
        max_bytes=128,
        retries=0,
    )
    assert "Hòa Phát" in csv

    monkeypatch.setattr(
        "app.secure_http.httpx.Client",
        lambda **kwargs: _Client(_Response([b"12345"])),
    )
    with pytest.raises(SecureFetchError, match="size limit"):
        fetch_authorized_csv(
            "https://licensed.example/report.csv",
            allowed_hosts={"licensed.example"},
            bearer_token=None,
            timeout_seconds=1,
            max_bytes=4,
            retries=0,
        )
