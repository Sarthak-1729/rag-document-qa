"""A small in-memory sliding-window rate limiter (per process, per client IP)."""

import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(
        self, limit: int, window_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> float | None:
        """Record a request. Return None if allowed, else seconds until a slot frees up."""
        if self.limit <= 0:
            return None
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return self.window - (now - hits[0])
            hits.append(now)
            return None

    def __call__(self, request: Request) -> None:
        # Behind a reverse proxy this is the proxy's IP; see README "Limitations".
        key = request.client.host if request.client else "unknown"
        retry_after = self.check(key)
        if retry_after is not None:
            raise HTTPException(
                429,
                "Too many questions. Please wait a moment and try again.",
                headers={"Retry-After": str(math.ceil(retry_after))},
            )
