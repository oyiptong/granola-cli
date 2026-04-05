from granola.ratelimit import RateLimiter


def test_compute_delay_respects_min_interval() -> None:
    limiter = RateLimiter(monotonic=lambda: 0.1, sleep=lambda _: None, jitter=lambda a, b: 0.0)
    limiter.record_request(now=0.0)
    assert limiter.compute_delay(now=0.1) == 0.1


def test_compute_delay_respects_rolling_window() -> None:
    limiter = RateLimiter(burst_capacity=2, window_seconds=5.0, sustained_rate_per_second=10.0, monotonic=lambda: 0.0)
    limiter.record_request(now=0.0)
    limiter.record_request(now=1.0)
    assert limiter.compute_delay(now=1.0) == 4.0


def test_prune_drops_old_timestamps() -> None:
    limiter = RateLimiter(burst_capacity=2, window_seconds=5.0, sustained_rate_per_second=10.0, monotonic=lambda: 0.0)
    limiter.record_request(now=0.0)
    limiter.record_request(now=1.0)
    assert limiter.compute_delay(now=6.1) == 0.0
