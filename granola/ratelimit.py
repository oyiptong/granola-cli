from __future__ import annotations

import logging
import random
import time
from collections import deque
from collections.abc import Callable

import requests


logger = logging.getLogger("granola.ratelimit")


class RateLimitExhaustedError(Exception):
    def __init__(self, retry_after_seconds: float | None = None):
        super().__init__("Rate limit retries exhausted")
        self.retry_after_seconds = retry_after_seconds


class TransientHttpError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"Transient HTTP error: {status_code}")
        self.status_code = status_code


class RateLimiter:
    def __init__(
        self,
        *,
        burst_capacity: int = 25,
        window_seconds: float = 5.0,
        sustained_rate_per_second: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[float, float], float] = random.uniform,
    ):
        self.burst_capacity = burst_capacity
        self.window_seconds = window_seconds
        self.min_interval = 1.0 / sustained_rate_per_second
        self.sleep = sleep
        self.monotonic = monotonic
        self.jitter = jitter
        self.timestamps: deque[float] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self.timestamps and self.timestamps[0] <= cutoff:
            self.timestamps.popleft()

    def compute_delay(self, *, now: float | None = None) -> float:
        now = self.monotonic() if now is None else now
        self._prune(now)
        delays = [0.0]
        if self.timestamps:
            delays.append(max(0.0, self.min_interval - (now - self.timestamps[-1])))
        if len(self.timestamps) >= self.burst_capacity:
            delays.append(max(0.0, self.window_seconds - (now - self.timestamps[0])))
        return max(delays)

    def wait_for_slot(self) -> None:
        delay = self.compute_delay()
        if delay > 0:
            self.sleep(delay)

    def record_request(self, *, now: float | None = None) -> None:
        timestamp = self.monotonic() if now is None else now
        self._prune(timestamp)
        self.timestamps.append(timestamp)

    def execute(self, operation: Callable[[], requests.Response], *, max_retries: int = 5) -> requests.Response:
        last_retry_after: float | None = None

        for attempt in range(max_retries + 1):
            self.wait_for_slot()
            self.record_request()
            try:
                response = operation()
            except requests.RequestException as exc:
                if attempt == max_retries:
                    raise exc
                logger.warning("retrying after network error: attempt=%s error=%s", attempt + 1, exc)
                self.sleep(self._backoff_seconds(attempt))
                continue

            if response.status_code == 429:
                retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                last_retry_after = retry_after
                if attempt == max_retries:
                    raise RateLimitExhaustedError(retry_after)
                logger.warning("retrying after 429 response: attempt=%s retry_after=%s", attempt + 1, retry_after)
                self.sleep(retry_after if retry_after is not None else self._backoff_seconds(attempt))
                continue

            if 500 <= response.status_code < 600:
                if attempt == max_retries:
                    raise TransientHttpError(response.status_code)
                logger.warning("retrying after server error: attempt=%s status=%s", attempt + 1, response.status_code)
                self.sleep(self._backoff_seconds(attempt))
                continue

            return response

        raise RateLimitExhaustedError(last_retry_after)

    def _backoff_seconds(self, attempt: int) -> float:
        base = min(2 ** attempt, 16)
        return base + self.jitter(0.0, 0.25)


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
