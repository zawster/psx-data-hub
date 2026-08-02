from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class _WindowLimiter:
    def __init__(self, capacity: int, window_seconds: int):
        self.capacity = capacity
        self.window_seconds = window_seconds
        self.buckets: dict[str, Deque[float]] = defaultdict(deque)
        self.lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            bucket = self.buckets[key]
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.capacity:
                return False
            bucket.append(now)
            return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 60, requests_burst: int = 10):
        super().__init__(app)
        self.minute = _WindowLimiter(requests_per_minute, 60)
        self.burst = _WindowLimiter(requests_burst, 10)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.endswith("/health") or request.url.path.endswith("/status"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        key = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token:
                key = f"bearer:{token[:24]}"
        if not key:
            key = request.headers.get("X-API-Key")
        if not key:
            key = request.client.host if request.client else "anon"
        if not key:
            key = "anon"

        if not self.minute.allow(key) or not self.burst.allow(key):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Lower polling frequency and retry later.",
                },
            )
        return await call_next(request)
