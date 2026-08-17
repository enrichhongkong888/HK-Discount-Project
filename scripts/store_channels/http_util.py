"""Shared async HTTP helpers for store-channel scrapers.

Uses a process-wide httpx.AsyncClient (TCP keep-alive / connection pooling)
gated by:
  - asyncio.Semaphore(15) global concurrency
  - stricter per-domain semaphores for anti-bot hosts (openrice / linkreit)

Timeouts: connect 3s, read 5s. Failed requests retry with exponential backoff
(max 2 retries) then degrade to the caller.
"""

from __future__ import annotations

import asyncio
import json
import ssl
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import httpx

DEFAULT_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CONNECT_TIMEOUT_S = 3.0
READ_TIMEOUT_S = 5.0
MAX_RETRIES = 2
GLOBAL_CONCURRENCY = 15

# Hostname suffix -> max in-flight requests (strict anti-bot targets).
DOMAIN_CONCURRENCY: dict[str, int] = {
    "openrice.com": 2,
    "linkreit.com": 3,
    "linkhk.com": 3,
}

HTTP_TIMEOUT = httpx.Timeout(
    connect=CONNECT_TIMEOUT_S,
    read=READ_TIMEOUT_S,
    write=READ_TIMEOUT_S,
    pool=CONNECT_TIMEOUT_S,
)
HTTP_LIMITS = httpx.Limits(
    max_connections=GLOBAL_CONCURRENCY + 5,
    max_keepalive_connections=GLOBAL_CONCURRENCY,
    keepalive_expiry=30.0,
)


class AsyncHttpRuntime:
    """Shared AsyncClient + semaphores for one expand / scrape session."""

    def __init__(self) -> None:
        self.client: httpx.AsyncClient | None = None
        self.global_sem = asyncio.Semaphore(GLOBAL_CONCURRENCY)
        self.domain_sems: dict[str, asyncio.Semaphore] = {
            host: asyncio.Semaphore(limit) for host, limit in DOMAIN_CONCURRENCY.items()
        }
        self._verify_ctx = True
        self._unverified_ctx = ssl.create_default_context()
        self._unverified_ctx.check_hostname = False
        self._unverified_ctx.verify_mode = ssl.CERT_NONE

    async def start(self) -> None:
        self.client = httpx.AsyncClient(
            headers=DEFAULT_UA,
            timeout=HTTP_TIMEOUT,
            limits=HTTP_LIMITS,
            follow_redirects=True,
            http2=False,
            verify=True,
        )

    async def aclose(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None


_runtime: AsyncHttpRuntime | None = None


def get_runtime() -> AsyncHttpRuntime:
    if _runtime is None:
        raise RuntimeError(
            "Async HTTP runtime is not active. "
            "Wrap callers in `async with shared_http():` (see expand_store_channels)."
        )
    return _runtime


@asynccontextmanager
async def shared_http() -> AsyncIterator[AsyncHttpRuntime]:
    """Install a global shared AsyncClient for the duration of the block."""
    global _runtime
    if _runtime is not None:
        # Nested reuse — keep outer client.
        yield _runtime
        return
    rt = AsyncHttpRuntime()
    await rt.start()
    _runtime = rt
    try:
        yield rt
    finally:
        _runtime = None
        await rt.aclose()


def _host_key(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None
    for suffix in DOMAIN_CONCURRENCY:
        if host == suffix or host.endswith("." + suffix):
            return suffix
    return None


def _backoff_delay(attempt: int) -> float:
    # attempt 0 -> first retry after 0.5s; attempt 1 -> 1.0s
    return 0.5 * (2**attempt)


async def afetch_text(
    url: str,
    *,
    timeout: float | httpx.Timeout | None = None,
    unverified_ssl: bool = False,
    headers: dict[str, str] | None = None,
) -> str:
    """GET url as text with pooling, concurrency limits, and backoff retries.

    On exhaustion of retries, raises the last exception so callers can degrade.
    ``timeout`` is accepted for API compatibility; connect/read caps still apply
    unless a full httpx.Timeout is passed.
    """
    rt = get_runtime()
    assert rt.client is not None
    req_timeout = timeout if isinstance(timeout, httpx.Timeout) else HTTP_TIMEOUT
    if isinstance(timeout, (int, float)):
        # Preserve legacy "overall" timeout intent while keeping connect short.
        req_timeout = httpx.Timeout(
            connect=min(CONNECT_TIMEOUT_S, float(timeout)),
            read=min(READ_TIMEOUT_S, float(timeout)),
            write=min(READ_TIMEOUT_S, float(timeout)),
            pool=CONNECT_TIMEOUT_S,
        )

    domain = _host_key(url)
    domain_sem = rt.domain_sems.get(domain) if domain else None
    last_exc: Exception | None = None
    attempts = 1 + MAX_RETRIES

    for attempt in range(attempts):
        try:
            async with rt.global_sem:
                if domain_sem is not None:
                    async with domain_sem:
                        return await _do_get_text(
                            rt,
                            url,
                            req_timeout,
                            unverified_ssl=unverified_ssl,
                            headers=headers,
                        )
                return await _do_get_text(
                    rt,
                    url,
                    req_timeout,
                    unverified_ssl=unverified_ssl,
                    headers=headers,
                )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            await asyncio.sleep(_backoff_delay(attempt))
            # Second try path: allow unverified SSL for middlebox / incomplete chains.
            unverified_ssl = True

    assert last_exc is not None
    raise last_exc


async def _do_get_text(
    rt: AsyncHttpRuntime,
    url: str,
    timeout: httpx.Timeout,
    *,
    unverified_ssl: bool,
    headers: dict[str, str] | None = None,
) -> str:
    assert rt.client is not None
    verify: bool | ssl.SSLContext = rt._unverified_ctx if unverified_ssl else True
    # Prefer the shared client; for unverified SSL open a one-shot client so we
    # do not permanently weaken the pooled session.
    if unverified_ssl:
        base = dict(DEFAULT_UA)
        if headers:
            base.update(headers)
        async with httpx.AsyncClient(
            headers=base,
            timeout=timeout,
            limits=HTTP_LIMITS,
            follow_redirects=True,
            verify=verify,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    resp = await rt.client.get(url, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return resp.text


async def afetch_json(
    url: str,
    *,
    timeout: float | httpx.Timeout | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any] | list[Any]:
    return json.loads(await afetch_text(url, timeout=timeout, headers=headers))


# --- Sync bridges (CLI / legacy callers outside shared_http) ---


def fetch_text(url: str, *, timeout: int = 45, unverified_ssl: bool = False) -> str:
    """Sync wrapper. Prefer ``afetch_text`` inside the expand asyncio pipeline."""

    async def _run() -> str:
        async with shared_http():
            return await afetch_text(url, timeout=timeout, unverified_ssl=unverified_ssl)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run())
    # Already inside an event loop: must use async API.
    raise RuntimeError("fetch_text() cannot be called from a running event loop; use afetch_text()")


def fetch_json(url: str, *, timeout: int = 60) -> dict[str, Any]:
    return json.loads(fetch_text(url, timeout=timeout))


def normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if digits.startswith("852") and len(digits) >= 11:
        digits = digits[3:]
    if len(digits) < 8:
        return ""
    digits = digits[-8:]
    return f"{digits[:4]} {digits[4:]}"
