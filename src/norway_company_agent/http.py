"""
Signalpost Agent — shared async HTTP client with throttling, retry, and
automatic evidence capture (content hash, timestamps, counters).

Usage::

    async with create_brreg_client() as client:
        resp = await client.get("/enhetsregisteret/api/enheter/123456789")
        print(resp.content_sha256, resp.status_code)

The module-level ``request_counter`` is an :class:`asyncio.Lock`-free
atomic counter (threading *and* asyncio safe) that the batch orchestrator
can read at any time to enforce the 2 000-request ceiling.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Self
from urllib.parse import urlparse

import httpx

from norway_company_agent.config import (
    BRREG_BASE_URL,
    BRREG_RATE_LIMIT_PER_MIN,
    DEFAULT_CONCURRENCY,
    DEFAULT_TIMEOUT,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

# ── Global request counter ───────────────────────────────────────────────────
# Thread-safe *and* async-safe because we only use atomic int operations
# via a threading.Lock (which is safe to hold briefly inside an async func).


class RequestCounter:
    """Thread-safe, globally-accessible request counter.

    The batch orchestrator can inspect ``.value`` at any point to decide
    whether the 2 000-request budget has been exhausted.
    """

    def __init__(self) -> None:
        self._value: int = 0
        self._lock: threading.Lock = threading.Lock()

    @property
    def value(self) -> int:
        return self._value

    def increment(self, n: int = 1) -> int:
        """Atomically add *n* and return the new total."""
        with self._lock:
            self._value += n
            return self._value

    def reset(self) -> None:
        with self._lock:
            self._value = 0

    def __repr__(self) -> str:
        return f"RequestCounter(value={self._value})"


request_counter = RequestCounter()

# ── HttpResponse ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Immutable value-object returned by every :class:`ThrottledClient` call.

    ``content_sha256`` is computed eagerly so callers can attach it as
    provenance evidence without touching the raw bytes again.
    """

    url: str
    final_url: str
    status_code: int
    content: bytes
    content_sha256: str
    retrieved_at: datetime
    headers: dict[str, str]
    elapsed_ms: int

    # Lazily decoded text — we store it eagerly to keep the dataclass frozen.
    text: str = field(default="", repr=False)

    @property
    def ok(self) -> bool:
        """``True`` when status is in the 2xx range."""
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        """Parse response content as JSON."""
        import json
        return json.loads(self.content)

    # ── Factory ──────────────────────────────────────────────────────────

    @classmethod
    def from_httpx(
        cls,
        response: httpx.Response,
        *,
        request_url: str,
        retrieved_at: datetime,
        elapsed_ms: int,
    ) -> HttpResponse:
        raw = response.content
        sha = hashlib.sha256(raw).hexdigest()
        try:
            text = response.text
        except Exception:
            text = raw.decode("utf-8", errors="replace")

        return cls(
            url=request_url,
            final_url=str(response.url),
            status_code=response.status_code,
            content=raw,
            content_sha256=sha,
            retrieved_at=retrieved_at,
            headers=dict(response.headers),
            elapsed_ms=elapsed_ms,
            text=text,
        )


# ── Per-domain token-bucket rate limiter ─────────────────────────────────────


class _TokenBucket:
    """Simple async token-bucket allowing *rate* requests per 60 s."""

    def __init__(self, rate_per_min: int) -> None:
        self._rate = rate_per_min
        self._tokens = float(rate_per_min)
        self._max = float(rate_per_min)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._max, self._tokens + elapsed * (self._rate / 60.0))
            self._last = now

            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / (self._rate / 60.0)
                logger.debug("Rate-limiter: sleeping %.2fs", wait)
                await asyncio.sleep(wait)
                self._tokens = 0.0
                self._last = time.monotonic()
            else:
                self._tokens -= 1.0


# ── ThrottledClient ──────────────────────────────────────────────────────────

# Retryable status codes
_RETRYABLE: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class ThrottledClient:
    """Async HTTP client with per-domain rate-limiting, concurrency cap,
    exponential-backoff retry, and automatic evidence capture.

    Use as an async context manager::

        async with ThrottledClient(rate_limit_per_min=25) as c:
            r = await c.get("https://example.com")
    """

    def __init__(
        self,
        *,
        base_url: str = "",
        rate_limit_per_min: int = 60,
        max_retries: int = 3,
        timeout: int = DEFAULT_TIMEOUT,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        self._base_url = base_url
        self._rate_limit = rate_limit_per_min
        self._max_retries = max_retries
        self._timeout = timeout

        self._semaphore = asyncio.Semaphore(concurrency)
        # domain → bucket
        self._buckets: dict[str, _TokenBucket] = {}
        self._bucket_lock = asyncio.Lock()

        self._client: httpx.AsyncClient | None = None

    # ── Context manager ──────────────────────────────────────────────────

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout, connect=10.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=DEFAULT_CONCURRENCY,
                max_keepalive_connections=DEFAULT_CONCURRENCY // 2,
            ),
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Internal helpers ─────────────────────────────────────────────────

    async def _bucket_for(self, url: str) -> _TokenBucket:
        domain = urlparse(url).netloc or "__default__"
        async with self._bucket_lock:
            if domain not in self._buckets:
                self._buckets[domain] = _TokenBucket(self._rate_limit)
            return self._buckets[domain]

    def _resolve_url(self, url: str) -> str:
        """Return fully-qualified URL (handles base_url prefixing)."""
        if url.startswith(("http://", "https://")):
            return url
        return f"{self._base_url.rstrip('/')}/{url.lstrip('/')}"

    # ── Public API ───────────────────────────────────────────────────────

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        """Issue a GET with rate-limiting, concurrency control, and retry.

        Returns an :class:`HttpResponse` regardless of status code.
        Raises only on unrecoverable transport errors after exhausting
        retries.
        """
        if self._client is None:
            raise RuntimeError(
                "ThrottledClient is not open. Use 'async with' or call __aenter__."
            )

        full_url = self._resolve_url(url)
        bucket = await self._bucket_for(full_url)

        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            await bucket.acquire()

            async with self._semaphore:
                start = time.monotonic()
                retrieved_at = datetime.now(timezone.utc)
                try:
                    raw_resp = await self._client.get(
                        url, params=params, headers=headers
                    )
                except httpx.HTTPError as exc:
                    elapsed_ms = int((time.monotonic() - start) * 1000)
                    logger.warning(
                        "HTTP error %s (attempt %d/%d, %dms): %s",
                        full_url,
                        attempt,
                        self._max_retries,
                        elapsed_ms,
                        exc,
                    )
                    last_exc = exc
                    if attempt < self._max_retries:
                        await asyncio.sleep(2 ** (attempt - 1))
                    continue

                elapsed_ms = int((time.monotonic() - start) * 1000)
                request_counter.increment()

                resp = HttpResponse.from_httpx(
                    raw_resp,
                    request_url=full_url,
                    retrieved_at=retrieved_at,
                    elapsed_ms=elapsed_ms,
                )

                logger.debug(
                    "%s %d (%dms, %s)",
                    full_url,
                    resp.status_code,
                    elapsed_ms,
                    resp.content_sha256[:12],
                )

                if resp.status_code not in _RETRYABLE or attempt == self._max_retries:
                    return resp

                # Retryable status — back off
                retry_after = raw_resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = min(int(retry_after), 30)
                else:
                    delay = 2 ** (attempt - 1)

                logger.info(
                    "Retryable %d from %s — sleeping %ds (attempt %d/%d)",
                    resp.status_code,
                    full_url,
                    delay,
                    attempt,
                    self._max_retries,
                )
                await asyncio.sleep(delay)

        # All retries exhausted with transport errors
        raise RuntimeError(
            f"All {self._max_retries} retries failed for {full_url}"
        ) from last_exc

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Convenience wrapper: GET → parse JSON → return dict, or ``None``
        if the request failed or the body is not valid JSON."""
        try:
            resp = await self.get(url, params=params, headers=headers)
        except Exception:
            logger.exception("get_json transport failure for %s", url)
            return None

        if not resp.ok:
            logger.warning("get_json non-2xx %d for %s", resp.status_code, resp.url)
            return None

        try:
            import json

            return json.loads(resp.content)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("get_json decode error for %s: %s", resp.url, exc)
            return None


# ── Pre-configured factory functions ─────────────────────────────────────────


def create_brreg_client() -> ThrottledClient:
    """Return a :class:`ThrottledClient` pre-configured for the
    Brønnøysund Register Centre APIs (conservative 25 req/min)."""
    return ThrottledClient(
        base_url=BRREG_BASE_URL,
        rate_limit_per_min=BRREG_RATE_LIMIT_PER_MIN,
        max_retries=3,
        timeout=DEFAULT_TIMEOUT,
    )


def create_web_client() -> ThrottledClient:
    """Return a :class:`ThrottledClient` for general web requests
    (60 req/min, no base URL)."""
    return ThrottledClient(
        rate_limit_per_min=60,
        max_retries=3,
        timeout=DEFAULT_TIMEOUT,
    )


def get_global_request_count() -> int:
    """Return the total number of outbound requests made across all clients."""
    return request_counter.value


def reset_global_request_count() -> None:
    """Reset the global outbound request counter."""
    request_counter.reset()


@dataclass
class FetchResult:
    url: str
    status: int
    elapsed_ms: int
    bytes_received: int
    body: Any = None
    error: str | None = None
    content_sha256: str | None = None
    retrieved_at: str | None = None
    effective_at: str | None = None


def fetch_json(url: str, *, timeout: float = 20.0, attempts: int = 3) -> FetchResult:
    """Synchronous JSON fetcher compatible with evaluator-owned replay harnesses."""
    import urllib.error
    import urllib.request

    last_error = "request failed"
    for attempt in range(attempts):
        started = time.monotonic()
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                elapsed = int((time.monotonic() - started) * 1000)
                now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                import json
                return FetchResult(
                    url=url,
                    status=response.status,
                    elapsed_ms=elapsed,
                    bytes_received=len(raw),
                    body=json.loads(raw),
                    content_sha256=hashlib.sha256(raw).hexdigest(),
                    retrieved_at=now_str,
                )
        except urllib.error.HTTPError as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            raw = exc.read()
            now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            if exc.code in {404, 410}:
                return FetchResult(
                    url=url,
                    status=exc.code,
                    elapsed_ms=elapsed,
                    bytes_received=len(raw),
                    error=f"HTTP {exc.code}",
                    content_sha256=hashlib.sha256(raw).hexdigest(),
                    retrieved_at=now_str,
                )
            last_error = f"HTTP {exc.code}"
        except Exception as exc:
            last_error = type(exc).__name__
        if attempt + 1 < attempts:
            time.sleep(0.4 * (2**attempt))
    now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return FetchResult(url, 0, 0, 0, error=last_error, retrieved_at=now_str)

