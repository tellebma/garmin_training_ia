"""Personal recovery baselines (E9.3): median 28d baseline + 7d trend.

Pure computation over (date, value) series. No DB here — the orchestrator
(recompute_recovery_baselines) lives in the same file's sibling once Task 2
adds it. Each metric yields a MetricBaseline; sleep yields a SleepBaseline
that also carries the raw duration/score baselines for display.
"""

from __future__ import annotations

import logging
import statistics
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, TypedDict, cast

from garmin_sync.supabase_client import get_admin_client

DbRows = list[dict[str, Any]]

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
    score_by_date = dict(score_samples)
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


log = logging.getLogger(__name__)


def _series(rows: list[dict[str, Any]], field: str) -> list[tuple[date, float]]:
    out: list[tuple[date, float]] = []
    for row in rows:
        raw_date = row.get("date")
        value = row.get(field)
        if raw_date is None or value is None:
            continue
        out.append((date.fromisoformat(str(raw_date)), float(value)))
    return out


def recompute_recovery_baselines(user_id: str) -> None:
    """Recompute the 5 recovery baselines over 28d and upsert. Never raises."""
    try:
        db = get_admin_client()
        today = date.today()
        start = (today - timedelta(days=WINDOW_DAYS)).isoformat()

        hrv_rows = cast(
            DbRows,
            db.table("hrv")
            .select("date, hrv_rmssd")
            .eq("user_id", user_id)
            .gte("date", start)
            .execute()
            .data
            or [],
        )
        sleep_rows = cast(
            DbRows,
            db.table("sleep")
            .select("date, sleep_duration_s, sleep_score")
            .eq("user_id", user_id)
            .gte("date", start)
            .execute()
            .data
            or [],
        )
        daily_rows = cast(
            DbRows,
            db.table("daily_metrics")
            .select("date, resting_hr, stress_avg, body_battery_high")
            .eq("user_id", user_id)
            .gte("date", start)
            .execute()
            .data
            or [],
        )

        hrv = compute_metric_baseline(
            _series(hrv_rows, "hrv_rmssd"), today=today, higher_is_better=True
        )
        resting_hr = compute_metric_baseline(
            _series(daily_rows, "resting_hr"), today=today, higher_is_better=False
        )
        stress = compute_metric_baseline(
            _series(daily_rows, "stress_avg"), today=today, higher_is_better=False
        )
        body_battery = compute_metric_baseline(
            _series(daily_rows, "body_battery_high"), today=today, higher_is_better=True
        )
        sleep = compute_sleep_baseline(
            _series(sleep_rows, "sleep_duration_s"),
            _series(sleep_rows, "sleep_score"),
            today=today,
        )

        row: dict[str, Any] = {
            "user_id": user_id,
            "computed_at": datetime.now(UTC).isoformat(),
            "hrv": hrv,
            "resting_hr": resting_hr,
            "sleep": sleep,
            "stress": stress,
            "body_battery": body_battery,
            "raw_meta": {"window_days": WINDOW_DAYS},
        }
        db.table("recovery_baselines").upsert(row, on_conflict="user_id").execute()
    except Exception:
        log.exception("recompute_recovery_baselines failed for user=%s", user_id)
