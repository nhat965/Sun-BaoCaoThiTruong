"""Bounded HTTPS CSV retrieval for explicitly authorized provider hosts."""

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx


class SecureFetchError(ValueError):
    pass


def _allowed_host(host: str, allowed_hosts: set[str]) -> bool:
    normalized = host.rstrip(".").lower()
    return normalized in allowed_hosts


def validate_https_destination(url: str, allowed_hosts: set[str]) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.port not in (None, 443)
    ):
        raise SecureFetchError(
            "Financial feed must use HTTPS port 443 without embedded credentials or fragments"
        )
    if not allowed_hosts or not _allowed_host(host, allowed_hosts):
        raise SecureFetchError("Financial feed host is not in FINANCIAL_CSV_ALLOWED_HOSTS")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise SecureFetchError("Financial feed DNS resolution failed") from exc
    if not addresses:
        raise SecureFetchError("Financial feed DNS returned no addresses")
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise SecureFetchError("Financial feed resolves to a non-public IP address")
    return host


def fetch_authorized_csv(
    url: str,
    *,
    allowed_hosts: set[str],
    bearer_token: str | None,
    timeout_seconds: float,
    max_bytes: int,
    retries: int,
    max_redirects: int = 2,
) -> str:
    original_host = validate_https_destination(url, allowed_hosts)
    current_url = url
    attempts = max(1, retries + 1)
    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for attempt in range(attempts):
            try:
                redirect_count = 0
                while True:
                    current_host = validate_https_destination(current_url, allowed_hosts)
                    headers = {"Accept": "text/csv, application/csv;q=0.9"}
                    if bearer_token and current_host == original_host:
                        headers["Authorization"] = f"Bearer {bearer_token}"
                    request = client.build_request("GET", current_url, headers=headers)
                    response = client.send(request, stream=True)
                    try:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location or redirect_count >= max_redirects:
                                raise SecureFetchError("Financial feed redirect is invalid or excessive")
                            next_url = urljoin(current_url, location)
                            next_host = validate_https_destination(next_url, allowed_hosts)
                            if next_host != original_host:
                                raise SecureFetchError(
                                    "Cross-host redirects are not allowed for authenticated CSV feeds"
                                )
                            current_url = next_url
                            redirect_count += 1
                            continue
                        response.raise_for_status()
                        content_length = response.headers.get("content-length")
                        if content_length and int(content_length) > max_bytes:
                            raise SecureFetchError("Financial feed exceeds the configured size limit")
                        content_type = response.headers.get("content-type", "").lower()
                        if content_type and not any(
                            value in content_type
                            for value in ("text/csv", "application/csv", "text/plain", "octet-stream")
                        ):
                            raise SecureFetchError("Financial feed content type is not CSV-compatible")
                        payload = bytearray()
                        for chunk in response.iter_bytes():
                            payload.extend(chunk)
                            if len(payload) > max_bytes:
                                raise SecureFetchError(
                                    "Financial feed exceeds the configured streaming size limit"
                                )
                        try:
                            return bytes(payload).decode("utf-8-sig", errors="strict")
                        except UnicodeDecodeError as exc:
                            raise SecureFetchError("Financial feed must be UTF-8 encoded") from exc
                    finally:
                        response.close()
            except httpx.HTTPStatusError as exc:
                # Retry only transient upstream failures. Client errors (including
                # auth/permission failures) are terminal and must not be masked.
                if exc.response.status_code < 500 or attempt + 1 >= attempts:
                    raise SecureFetchError(
                        "Financial feed returned a non-success HTTP status"
                    ) from exc
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                if attempt + 1 >= attempts:
                    raise SecureFetchError("Financial feed request failed after bounded retries")
        raise SecureFetchError("Financial feed request failed")
