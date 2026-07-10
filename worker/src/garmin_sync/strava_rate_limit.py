"""App-wide (not per-user) sliding-window rate limiter for the Strava API.

Strava enforces 100 req/15min and 1000/day per *application* (shared across
all our users), not per athlete. A simple in-memory timestamp list is enough
for MVP scale (mono-instance worker) — same acceptable lost-on-restart
semantics as the cooldown tracking in connect.py.
"""

from __future__ import annotations

import time
from collections import deque

_MAX_PER_15MIN = 100
_MAX_PER_DAY = 1000
_WINDOW_15MIN_S = 15 * 60
_WINDOW_DAY_S = 24 * 60 * 60

_calls_15min: deque[float] = deque()
_calls_daily: deque[float] = deque()


class StravaRateLimitExceeded(Exception):
    """Raised when the app-wide Strava budget is exhausted."""


def _purge(bucket: deque[float], window_s: int, now: float) -> None:
    while bucket and now - bucket[0] > window_s:
        bucket.popleft()


def check_or_raise() -> None:
    now = time.time()
    _purge(_calls_15min, _WINDOW_15MIN_S, now)
    _purge(_calls_daily, _WINDOW_DAY_S, now)
    if len(_calls_15min) >= _MAX_PER_15MIN:
        raise StravaRateLimitExceeded("Strava 15-minute budget exhausted")
    if len(_calls_daily) >= _MAX_PER_DAY:
        raise StravaRateLimitExceeded("Strava daily budget exhausted")


def record_call() -> None:
    now = time.time()
    _calls_15min.append(now)
    _calls_daily.append(now)
