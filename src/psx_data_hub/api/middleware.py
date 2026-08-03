from __future__ import annotations

import time
from collections import OrderedDict, defaultdict, deque
from threading import Lock
from typing import Deque, Iterable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Paths that are exempt from rate limiting. Match must be EXACT (or under the
# API prefix). Suffix matching like ".endswith('/health')" made it too easy to
# craft bypass paths like `/foo/health` (BUG-7).
_EXEMPT_PATHS = {"/v1/health", "/v1/status", "/health", "/status"}


class _WindowLimiter:
    def __init__(self, capacity: int, window_seconds: int, max_buckets: int = 10_000):
        self.capacity = capacity
        self.window_seconds = window_seconds
        self.max_buckets = max(1, max_buckets)
        # OrderedDict lets us evict the least-recently-used bucket cheaply.
        self.buckets: "OrderedDict[str, Deque[float]]" = OrderedDict()
        self.lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            bucket = self.buckets.get(key)
            if bucket is None:
                bucket = deque()
                self.buckets[key] = bucket
            else:
                # Mark this bucket as recently used.
                self.buckets.move_to_end(key)
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.capacity:
                return False
            bucket.append(now)

            # Bound total memory by evicting cold buckets.
            while len(self.buckets) > self.max_buckets:
                self.buckets.popitem(last=False)
            return True


def _extract_client_key(
    request: Request,
    *,
    trusted_proxies: Iterable[str],
) -> str:
    """Prefer bearer/api-key identifiers; fall back to a client IP.

    When the request comes from a configured trusted proxy the client IP is
    taken from the first entry of `X-Forwarded-For`. Otherwise the direct
    peer address is used (BUG-7).
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            return f"bearer:{token[:24]}"

    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"apikey:{api_key[:24]}"

    peer_host = request.client.host if request.client else None
    if peer_host and peer_host in set(trusted_proxies):
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return f"ip:{first}"

    return f"ip:{peer_host or 'anon'}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_burst: int = 10,
        max_buckets: int = 10_000,
        trusted_proxies: Iterable[str] | None = None,
    ):
        super().__init__(app)
        self.minute = _WindowLimiter(requests_per_minute, 60, max_buckets=max_buckets)
        self.burst = _WindowLimiter(requests_burst, 10, max_buckets=max_buckets)
        self.trusted_proxies = tuple(trusted_proxies or ())

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        key = _extract_client_key(request, trusted_proxies=self.trusted_proxies)

        if not self.minute.allow(key) or not self.burst.allow(key):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Lower polling frequency and retry later.",
                },
            )
        return await call_next(request)


class HideServerHeaderMiddleware(BaseHTTPMiddleware):
    """Drop the `Server: uvicorn` header on outgoing responses (BUG-23)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if "server" in response.headers:
            del response.headers["server"]
        return response
