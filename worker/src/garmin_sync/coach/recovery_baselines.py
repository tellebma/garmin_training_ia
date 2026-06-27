"""Personal recovery baselines (E9.3): median 28d baseline + 7d trend.

Pure computation over (date, value) series. No DB here — the orchestrator
(recompute_recovery_baselines) lives in the same file's sibling once Task 2
adds it. Each metric yields a MetricBaseline; sleep yields a SleepBaseline
that also carries the raw duration/score baselines for display.
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Literal, TypedDict

WINDOW_DAYS = 28
RECENT_DAYS = 7
STABLE_THRESHOLD = 0.05
CONFIDENCE_HIGH = 21
CONFIDENCE_MEDIUM = 10
FRESHNESS_MAX_AGE_DAYS = 2
SLEEP_DURATION_CAP_S = 28800  # 8 hours

Trend = Literal["improving", "stable", "declining", "no_data"]
Confidence = Literal["high", "medium", "low", "no_data"]
Freshness = Literal["fresh", "stale", "no_data"]


class MetricBaseline(TypedDict):
    baseline: float | None
    recent: float | None
    trend: Trend
    confidence: Confidence
    freshness: Freshness
    days_covered: int
    last_date: str | None


class SleepBaseline(MetricBaseline):
    duration_baseline_s: int | None
    duration_recent_s: int | None
    score_baseline: int | None
    score_recent: int | None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _confidence(days_covered: int) -> Confidence:
    if days_covered == 0:
        return "no_data"
    if days_covered >= CONFIDENCE_HIGH:
        return "high"
    if days_covered >= CONFIDENCE_MEDIUM:
        return "medium"
    return "low"


def _freshness(last: date | None, today: date) -> Freshness:
    if last is None:
        return "no_data"
    return "fresh" if (today - last).days <= FRESHNESS_MAX_AGE_DAYS else "stale"


def _trend(baseline: float | None, recent: float | None, *, higher_is_better: bool) -> Trend:
    if baseline is None or recent is None:
        return "no_data"
    if baseline <= 0:
        return "stable"
    delta = (recent - baseline) / baseline
    if abs(delta) <= STABLE_THRESHOLD:
        return "stable"
    raw_up = delta > 0
    improving = raw_up if higher_is_better else not raw_up
    return "improving" if improving else "declining"


def compute_metric_baseline(
    samples: list[tuple[date, float]],
    *,
    today: date,
    higher_is_better: bool,
) -> MetricBaseline:
    """Median 28d baseline + 7d recent trend for one metric."""
    window_start = today - timedelta(days=WINDOW_DAYS)
    recent_start = today - timedelta(days=RECENT_DAYS)
    in_window = [(d, v) for d, v in samples if window_start <= d <= today]

    baseline = _median([v for _d, v in in_window])
    recent = _median([v for d, v in in_window if d >= recent_start])
    days_covered = len({d for d, _v in in_window})
    last_date = max((d for d, _v in in_window), default=None)

    return MetricBaseline(
        baseline=baseline,
        recent=recent,
        trend=_trend(baseline, recent, higher_is_better=higher_is_better),
        confidence=_confidence(days_covered),
        freshness=_freshness(last_date, today),
        days_covered=days_covered,
        last_date=last_date.isoformat() if last_date else None,
    )


def _sleep_index(duration_s: float, score: float) -> float:
    norm_duration = min(duration_s / SLEEP_DURATION_CAP_S, 1.0)
    return (norm_duration + score / 100.0) / 2.0 * 100.0


def compute_sleep_baseline(
    duration_samples: list[tuple[date, float]],
    score_samples: list[tuple[date, float]],
    *,
    today: date,
) -> SleepBaseline:
    """Combine duration + score into one trend, keep raw baselines for display."""
    score_by_date = {d: s for d, s in score_samples}
    index_samples = [
        (d, _sleep_index(dur, score_by_date[d]))
        for d, dur in duration_samples
        if d in score_by_date
    ]
    base = compute_metric_baseline(index_samples, today=today, higher_is_better=True)

    window_start = today - timedelta(days=WINDOW_DAYS)
    recent_start = today - timedelta(days=RECENT_DAYS)
    dur_window = [(d, v) for d, v in duration_samples if window_start <= d <= today]
    score_window = [(d, v) for d, v in score_samples if window_start <= d <= today]
    dur_base = _median([v for _d, v in dur_window])
    dur_recent = _median([v for d, v in dur_window if d >= recent_start])
    score_base = _median([v for _d, v in score_window])
    score_recent = _median([v for d, v in score_window if d >= recent_start])

    return SleepBaseline(
        **base,
        duration_baseline_s=int(dur_base) if dur_base is not None else None,
        duration_recent_s=int(dur_recent) if dur_recent is not None else None,
        score_baseline=int(score_base) if score_base is not None else None,
        score_recent=int(score_recent) if score_recent is not None else None,
    )
